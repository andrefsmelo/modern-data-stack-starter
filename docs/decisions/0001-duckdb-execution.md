# ADR-0001: DuckDB execution location and state management

- **Status:** Accepted
- **Date:** 2026-04-25
- **Deciders:** Data engineering owner

## Context

In Phase 1 the platform runs `dbt + DuckDB` against Parquet files stored in S3. DuckDB is an embedded engine — there is no server. That leaves two open questions the original architecture document did not answer:

1. **Where does the `dbt` invocation actually run?** A developer laptop, a long-lived VM, or an ephemeral CI runner?
2. **Where does the resulting `.duckdb` database file live between runs?** It holds materialized tables, incremental state, and dbt's `manifest.json` build cache.

If these are not pinned down, the team accumulates incompatible local databases, "works on my machine" bugs in incremental models, and an unclear story for production dashboards.

## Decision

### Execution: GitHub Actions runners, not a persistent VM

All scheduled `dbt run` / `dbt test` invocations execute inside **GitHub Actions** on the standard `ubuntu-latest` runner. No dedicated VM is provisioned for DuckDB compute.

Rationale:
- Zero idle cost — runners are billed only while jobs execute.
- Environment is reproducible from `.github/workflows/` and a pinned `requirements.txt`.
- Logs, artifacts, and notifications are already first-class in GitHub Actions.
- A single `ubuntu-latest` runner has 4 vCPU and 16 GB RAM, which is sufficient for DuckDB on hundreds of GB of Parquet when models are partition-pruned.

### State: `prod.duckdb` round-trips through S3

The production DuckDB file is treated as a build artifact, not a server:

1. At the start of each scheduled run, the workflow downloads `s3://{bucket}/state/prod.duckdb` to the runner.
2. `dbt run` / `dbt test` execute against the local file. Sources are read directly from S3 via DuckDB's `httpfs` extension.
3. On success, the updated `.duckdb` file is uploaded back to `s3://{bucket}/state/prod.duckdb`, with the previous version retained via S3 object versioning for rollback.
4. On failure, the file is **not** uploaded; the previous good state is preserved and the next run resumes from it.

A workflow-level concurrency group (`group: dbt-prod`) guarantees only one `prod` job runs at a time, preventing concurrent writers to the same state file.

### Developer workflow

- Developers run `dbt` locally against a separate `dev.duckdb` file that they create on demand from `dev/` S3 prefixes.
- Developers never read or write `prod.duckdb`. To debug production, they download a copy with `aws s3 cp` and inspect it read-only.

### Downstream consumers

A future BI/visualization layer is expected to read from a **read-only copy** of `prod.duckdb`, refreshed after each successful `dbt run`. No live consumer is wired up in the current phase.

## Consequences

**Positive**
- One unambiguous answer to "where does production data live" (S3, with `.duckdb` as a derived cache).
- Cheap to operate — no compute VM, no managed warehouse.
- Disaster recovery is trivial — S3 versioning gives point-in-time rollback of the entire warehouse.

**Negative**
- Each run pays the cost of downloading `prod.duckdb`. Acceptable while the file stays under ~5 GB; revisit when it exceeds that.
- A future BI consumer will pay a small staleness window (minutes between dbt run and refresh). Acceptable for daily/hourly dashboards; not acceptable for sub-minute SLAs (out of scope for Phase 1).
- Concurrency cap of 1 means long-running models block subsequent schedules. Mitigated by tagging models so heavy reprocessing runs in its own workflow.

## Alternatives Considered

- **Persistent VM hosting `prod.duckdb`**: rejected. Adds 24/7 cost, an OS to patch, and a single point of failure. The S3 round-trip pattern gives the same correctness with none of these.
- **MotherDuck (managed DuckDB)**: viable, but introduces a paid SaaS dependency that the Phase 1 budget explicitly avoids. Reconsider in Phase 2 as an alternative to BigQuery / Snowflake.
- **Local-only execution from a developer laptop**: rejected. Production runs cannot depend on a human being awake.
