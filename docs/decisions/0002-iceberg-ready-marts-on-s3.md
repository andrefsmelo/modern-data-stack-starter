# ADR-0002: Iceberg-ready marts on S3 for multi-engine read access

- **Status:** Proposed
- **Date:** 2026-04-28
- **Deciders:** Data engineering owner

## Context

Phase 1 lands the warehouse in a single `prod.duckdb` file in S3 (see [ADR-0001](0001-duckdb-execution.md)). That works while DuckDB is the only consumer, but the architecture promises that other warehouses (BigQuery, Snowflake, Athena, Trino, Spark) can be added later without re-platforming. A `.duckdb` blob is not readable by those engines — they expect either columnar files in object storage or a managed-warehouse table.

Two questions:

1. **Should the marts also be written somewhere other engines can read?**
2. **If yes — full Apache Iceberg now, or a lighter "Iceberg-ready" Parquet layout?**

Either choice has to fit the Phase 1 constraints: ~$30/month budget, one operator, no proprietary lock-in, ephemeral compute only.

## Decision

### Mart export to S3 in a partitioned Parquet layout

After every successful `dbt build`, the workflow exports each mart table to:

```
s3://${S3_BUCKET}/marts/<table_name>/year=YYYY/month=MM/day=DD/<table_name>.parquet
```

Files are written by a small post-build Python step that uses DuckDB to read from `prod.duckdb` and write Parquet directly to S3 via `httpfs`. No new compute, no new dependencies the runner doesn't already have.

### AWS Glue Data Catalog for table metadata

Each exported mart is registered as an external table in **AWS Glue Data Catalog** under the database `modern_data_stack_marts`. Schema is declared via Athena `CREATE EXTERNAL TABLE` DDL committed to the repo (one `.sql` file per mart in `transformation/exports/`). No Glue Crawlers — the schema is known, deterministic, and version-controlled with the dbt models.

This is enough to make the marts queryable from:

- **Athena** — directly, no extra config.
- **Snowflake** — via [external tables](https://docs.snowflake.com/en/user-guide/tables-external-intro) pointing at the same S3 prefix.
- **BigQuery** — via [BigLake tables](https://cloud.google.com/bigquery/docs/biglake-intro) referencing the Glue catalog.
- **Trino / Spark** — via the Hive connector pointing at Glue.
- **DuckDB itself** — `read_parquet('s3://.../marts/<table>/year=*/month=*/day=*/*.parquet')` — useful for lightweight consumers that don't want to download the whole `prod.duckdb`.

### What this is *not*: full Apache Iceberg

We deliberately stop short of Iceberg metadata, snapshots, manifest files, and a REST/Glue Iceberg catalog. The "Iceberg-ready" framing means: **the partition layout is compatible**, so a future migration to Iceberg is a one-shot metadata-write step, not a re-shaping of the data.

Iceberg-specific features we do **not** get from this ADR (and don't need yet):

- ACID writes from concurrent writers
- Snapshot isolation / time travel
- Schema evolution metadata
- Multi-engine *write* (level-1 is read-many, write-one)

When any of those become hard requirements, ADR-000X-iceberg-marts.md will replace this one. The trigger is documented in [evolution-triggers.md](../evolution-triggers.md).

## Consequences

**Positive**

- Marts are now queryable from any modern data warehouse without copying data into that warehouse.
- Glue Catalog free tier covers our scale (5 marts × ~90 partitions ≈ 500 objects vs. 1M free) — operational cost stays at ~$0/month additive.
- Existing `prod.duckdb` round-trip pattern is unchanged. Marts in S3 are an **additional** sink, not a replacement.
- Schema DDL lives in the repo and is reviewed alongside model changes — no out-of-band schema drift.
- Migration path to Iceberg is well-defined: same Parquet files, add an Iceberg metadata layer on top.

**Negative**

- Two copies of the marts now exist (`prod.duckdb` + Parquet on S3). They can drift if the export step fails after a successful dbt build — mitigated by running the export as part of the same workflow with `set -e`.
- Schema changes require a manual `ALTER TABLE` DDL update, not just a dbt re-run. Acceptable at this scale; Glue Crawlers would automate it but cost ~$3-6/month and re-introduce schema drift risk.
- Without snapshots, a bad export can overwrite a partition. Mitigated by writing date-partitioned files (so each run only touches today's partition) and by S3 object versioning being enabled on the bucket.

## Alternatives Considered

- **Stick with `prod.duckdb` only.** Rejected: blocks the "other warehouse can join in" promise the architecture makes; one of the project's stated next-steps.
- **Full Iceberg now via `pyiceberg` + Glue Iceberg catalog.** Rejected for Phase 1: experimental write path in DuckDB, more moving parts, no current need for ACID/time-travel. Re-evaluate when concurrent writers or schema evolution becomes a real requirement.
- **Glue Crawlers instead of static DDL.** Rejected: $3-6/month for a problem (schema drift) we don't have, and crawlers can mis-infer types in ways that break consumers silently.
- **`dbt-glue` adapter writing directly to Glue.** Rejected: requires Glue ETL jobs (Spark) which costs money per run and is heavy for our data volumes.

## Implementation outline

When this ADR is accepted, scope of the follow-up PR:

1. `transformation/exports/<table>.sql` — `CREATE EXTERNAL TABLE` DDL for each mart.
2. `transformation/exports/export_marts.py` — DuckDB → S3 Parquet writer; reads `prod.duckdb`, writes one partition per mart per run.
3. `.github/workflows/dbt-build.yml` — new step after `dbt build`, before the `prod.duckdb` upload, calling `export_marts.py`.
4. `orchestration/README.md` — note the new IAM permissions: `glue:GetDatabase`, `glue:GetTable`, `glue:CreatePartition` on the `modern_data_stack_marts` database, and `s3:PutObject` on `s3://<bucket>/marts/*` (the existing bucket policy from ADR-0001 already grants the bucket-level ones).
5. `docs/marts.md` — append a "Querying from outside DuckDB" section with Athena and Snowflake examples.
6. `docs/evolution-triggers.md` — add the level-2 trigger (move to full Iceberg when ACID/time-travel/concurrent writers are required).
