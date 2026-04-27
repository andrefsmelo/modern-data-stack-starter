# Architecture

> The architectural reasoning behind this repo: layers, costs, conventions, and the per-layer upgrade path.

-----

## Overview

The platform is designed for a context where moving fast, keeping infrastructure cost low, and avoiding architectural dead ends all matter at the same time — a single data engineer (or one-and-a-half) supporting a company up to ~50 people. The stack is intentionally minimal at first, with a clear upgrade path at each layer as data volume, source count, or team size grows.

For the operational signals that should drive a move between phases or tools, see [evolution-triggers.md](evolution-triggers.md). For the ingestion-tool landscape and decision matrix (Airbyte vs. dlt vs. Meltano vs. Fivetran vs. CDC vs. OCR), see [ingestion.md](ingestion.md). For ephemeral compute, GitHub Actions pricing, and the escape hatches when it doesn't fit (Lambda, Fargate, Modal, Cloud Run), see [orchestration.md](orchestration.md).

-----

## Goals

- Keep infrastructure cost under ~$40/month in the early stage
- Avoid vendor lock-in by using open formats (Parquet, Iceberg) and portable tools
- Enable a single data engineer to own and operate the full platform
- Provide a clear migration path for each layer as data volume grows
- Serve as a reusable blueprint for future projects

-----

## Non-Goals

- Real-time / streaming pipelines
- Change-Data-Capture (CDC) from operational databases
- Multi-region or high-availability setup
- Enterprise governance and cataloging tooling (DataHub, Collibra, Atlan)
- PII / GDPR tooling (masking, subject-access requests, retention automation)
- Reverse-ETL (syncing modeled data back into SaaS tools)
- ML feature stores or model serving

-----

## Architecture

### Layers

```
Ingestion → Storage → Transformation → Orchestration → Observability
```

A visualization layer is part of the design but intentionally not implemented in the bootstrap phase — the chosen tool reads `prod.duckdb` directly, so it can be added without changing any upstream layer.

### Phase 1 (0-6 months) — Bootstrap

|Layer         |Tool                                  |Rationale                                          |
|--------------|--------------------------------------|---------------------------------------------------|
|Ingestion     |Airbyte (self-hosted) + dlt / Python  |Connectors for SaaS + lightweight code for custom APIs|
|Storage       |Amazon S3                             |Industry-standard, mature ecosystem, cheap at small scale|
|Format        |Parquet (Iceberg-ready layout)        |Open standard, partition layout compatible with Iceberg later|
|Transformation|dbt Core + DuckDB                     |Zero license cost, handles 100s of GB on a single node|
|Orchestration |GitHub Actions (cron schedules)       |Ephemeral runners, $0 in the free tier for typical use; see [orchestration.md](orchestration.md)|
|Observability |GitHub Actions notifications → Slack  |Free, surfaces failures where the team already lives|

### Phase 2 (6-18 months) — Growth

|Layer            |Tool                             |Trigger to migrate                                   |
|-----------------|---------------------------------|-----------------------------------------------------|
|Storage          |S3 + Apache Iceberg              |Need ACID writes, schema evolution, time travel, or multi-engine reads|
|Compute          |BigQuery (on-demand) or Snowflake|DuckDB query latency consistently > 5 min on tuned models, or raw volume > 200 GB|
|Transformation   |dbt Core in CI (GitHub Actions) + scheduled BigQuery/Snowflake runs|Team size grows; need scheduled runs and tested artifacts|
|Orchestration    |Prefect Cloud or Dagster Cloud   |More than 10 pipelines or non-trivial dependencies   |
|Ingestion        |Airbyte Cloud or dedicated VM    |Source count > 10, or self-hosted Airbyte memory pressure|
|Observability    |Sentry / Grafana Cloud + dbt artifacts|Failures across multiple systems require a single pane|

### Phase 3 (18+ months) — Scale

|Layer         |Tool                             |
|--------------|---------------------------------|
|Storage       |S3 + Apache Iceberg or Delta Lake|
|Compute       |Spark on Databricks or EMR, Trino, or Snowflake at scale|
|Transformation|dbt Cloud                        |
|Orchestration |Dagster or Apache Airflow        |
|Observability |Datadog / OpenTelemetry + Monte Carlo or Elementary|

-----

## Cost Estimate — Phase 1

VM sizes are calibrated against actual memory needs (Airbyte JVM ≈ 4 GB).

|Component                         |Monthly Cost   |
|----------------------------------|---------------|
|Amazon S3 (≤ 10 GB + low requests)|~$1            |
|dbt Core                          |$0             |
|DuckDB                            |$0             |
|Airbyte (self-hosted, 4 GB VM)    |~$20           |
|GitHub Actions (free tier)        |$0             |
|Slack (free tier)                 |$0             |
|**Total**                         |**~$20-25/mo** |

If $20/mo is still too high, swap Airbyte for [dlt](https://dlthub.com) running inside GitHub Actions — that drops the Airbyte VM entirely and brings the budget to ~$1/mo, at the cost of writing more connector code.

-----

## Data Flow

```
External Sources
      │
      ▼
[Ingestion Layer]
Airbyte / dlt / Python scripts
      │
      ▼
[Raw Storage]
Amazon S3 — Parquet files (Iceberg-ready layout)
      │
      ▼
[Transformation Layer]
dbt Core + DuckDB
      │
      ├── staging/        (clean, typed, renamed)
      ├── intermediate/   (joins, business rules)
      └── marts/          (final models for BI)
      │
      ▼
[Observability]
GitHub Actions → Slack alerts; dbt artifacts archived to S3
```

DuckDB execution location and state handling are pinned in [decisions/0001-duckdb-execution.md](decisions/0001-duckdb-execution.md).

-----

## Conventions

### Naming

- Tables: `snake_case`
- dbt models: prefixed by layer (`stg_`, `int_`, `fct_`, `dim_`)
- S3 paths: `s3://{bucket}/raw/{source}/{entity}/year={yyyy}/month={mm}/day={dd}/`
- Bucket naming: `{org}-data-{env}` (e.g. `acme-data-prod`, `acme-data-dev`)

### Environments

- Two S3 prefixes per bucket: `prod/` and `dev/`. Developers read from `prod/raw/` but write modeled outputs only to `dev/`.
- Two DuckDB files: `prod.duckdb` (CI-managed, pulled from S3 before each run, pushed back after) and `dev.duckdb` (local, ephemeral).
- dbt targets `prod` and `dev` mirror the above.

### Ingestion: choosing a tool

The default rule (use this for day-to-day calls):

1. **Engineering-led team, 1–5 SaaS sources** → `dlt` pipeline in GitHub Actions. No server, no VM bill.
2. **Mixed team where non-engineers add sources** → self-hosted **Airbyte** (4 GB VM).
3. **Engineering-led, 5–15 SaaS sources, want pre-built coverage without the JVM** → **Meltano**.
4. **Source is exotic (binary file drops, scraping, vendor SDK)** → custom Python script invoked from GitHub Actions, writing Parquet to S3 with the same path convention.
5. **Single source produces > 10 GB/day** → peel it off and use **Sling** or a dedicated dlt job. Don't scale the general-purpose tool for a bulk source.

Document the choice and rationale in the ingestion source's README.

When the rule does not fit (managed-vendor evaluation, CDC, > 15 sources, > 20 engineers), see the full landscape and decision matrix in [ingestion.md](ingestion.md).

### Secrets

- All secrets live in **GitHub Actions Secrets** (org or repo level).
- Local development uses a `.env` file ignored by git, populated from a shared 1Password vault.
- No secrets in dbt `profiles.yml` — use `env_var()` exclusively.

### Schema Evolution

- All raw Parquet writes include a `_ingested_at` timestamp and a `_schema_version` integer.
- Breaking schema changes (column drop, type narrow) require a new `_schema_version` and a parallel staging model until the old version ages out.
- `dbt source freshness` runs in CI; staleness > 24 h alerts to Slack.

### Data Quality

dbt tests are tagged by severity to prevent alert fatigue:

- `severity: error` — blocks the pipeline. Reserved for primary-key uniqueness, not-null on join keys, and accepted-values on enums consumed by dashboards.
- `severity: warn` — logs a warning and posts to Slack but does not block downstream models. Default for all other tests.
- Every staging model has at least one `error`-level uniqueness test on its primary key.
- Every source has at least one `dbt source freshness` check.

### Documentation

- Every dbt model must have a description in `schema.yml`
- `dbt docs` is generated in CI and published to GitHub Pages on `main`
- Architecture decisions documented as ADRs in `docs/decisions/`

-----

## Tools Not Used (and Why)

|Tool              |Reason skipped                                      |
|------------------|----------------------------------------------------|
|Apache Kafka      |Overkill without real streaming requirements        |
|Databricks        |High cost and operational complexity for small teams|
|Amazon Redshift   |Fixed instance cost, not suited for early stage     |
|Fivetran          |Per-row pricing dominates the budget at low volume  |
|DataHub / Atlan   |High maintenance overhead, premature optimization   |
|Tableau / Power BI|License cost not justified at this stage            |
|Cloudflare R2     |Considered for zero-egress; rejected because S3's tooling ecosystem (Iceberg, Athena, BigQuery external tables) is materially deeper. Revisit if egress costs ever exceed ~$50/mo.|

-----

## Migration Triggers (Summary)

The high-level signals to move from Phase 1 to Phase 2 are:

- Query runtime on DuckDB consistently exceeds 5 minutes after tuning
- Raw data volume surpasses 200 GB
- More than 10 active pipelines in production
- More than 10 ingestion sources, or Airbyte VM consistently OOMs
- A second data engineer joins the team
- Stakeholders require SLA guarantees on dashboard freshness

For the **full operational playbook** — per-layer triggers, what to do when each fires, and intermediate options that defer a Phase 2 jump — see [evolution-triggers.md](evolution-triggers.md).

-----

## References

- [dbt Documentation](https://docs.getdbt.com)
- [DuckDB Documentation](https://duckdb.org/docs)
- [dlt Documentation](https://dlthub.com/docs)
- [Airbyte Documentation](https://docs.airbyte.com)
- [Apache Iceberg](https://iceberg.apache.org)
- [Amazon S3 Pricing](https://aws.amazon.com/s3/pricing/)
