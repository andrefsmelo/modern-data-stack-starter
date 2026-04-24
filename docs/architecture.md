# Architecture

> A lightweight, cost-effective data platform blueprint for early-stage startups, designed to grow with your business.

-----

## Overview

This project documents and implements a production-ready data platform designed for small startups that need to move fast, keep costs low, and avoid architectural dead ends. The stack is intentionally minimal at first, with a clear upgrade path at each layer as the business scales.

-----

## Goals

- Keep infrastructure cost under $20/month in the early stage
- Avoid vendor lock-in by using open formats and portable tools
- Enable a single data engineer to own and operate the full platform
- Provide a clear migration path for each layer as data volume grows
- Serve as a reusable blueprint for future projects

-----

## Non-Goals

- Real-time / streaming pipelines (out of scope for this phase)
- Multi-region or high-availability setup
- Enterprise governance and cataloging tooling

-----

## Architecture

### Layers

```
Ingestion → Storage → Transformation → Orchestration → Visualization
```

### Phase 1 (0-6 months) — Bootstrap

|Layer         |Tool                                  |Rationale                                          |
|--------------|--------------------------------------|---------------------------------------------------|
|Ingestion     |Airbyte (self-hosted) + Python scripts|Ready-made connectors + flexibility for custom APIs|
|Storage       |Cloudflare R2                         |S3-compatible, no egress fees, generous free tier  |
|Format        |Parquet                               |Open standard, compatible with any downstream tool |
|Transformation|dbt Core + DuckDB                     |Zero cost, runs locally, handles GBs with ease     |
|Orchestration |GitHub Actions / cron                 |No new infrastructure, sufficient for few pipelines|
|Visualization |Metabase (self-hosted)                |Free, easy to use, self-contained                  |

### Phase 2 (6-18 months) — Growth

|Layer            |Tool                             |Trigger to migrate                                   |
|-----------------|---------------------------------|-----------------------------------------------------|
|Storage + Compute|BigQuery (on-demand) or Snowflake|Data volume > 50 GB or query latency becomes an issue|
|Transformation   |dbt Core in CI (GitHub Actions)  |Team size grows, need for scheduled runs and testing |
|Orchestration    |Prefect Cloud or Dagster Cloud   |More than 10 pipelines, dependency management needed |
|Visualization    |Metabase or Looker Studio        |BI needs expand beyond simple dashboards             |

### Phase 3 (18+ months) — Scale

|Layer         |Tool                             |
|--------------|---------------------------------|
|Storage       |S3 + Delta Lake or Apache Iceberg|
|Compute       |Spark on Databricks or EMR       |
|Transformation|dbt Cloud                        |
|Orchestration |Dagster or Apache Airflow        |
|Visualization |Looker or custom tooling         |

-----

## Cost Estimate — Phase 1

|Component                    |Monthly Cost  |
|-----------------------------|--------------|
|Cloudflare R2 (up to 10 GB)  |$0            |
|dbt Core                     |$0            |
|DuckDB                       |$0            |
|Metabase (self-hosted, $5 VM)|~$5           |
|Airbyte (self-hosted, $10 VM)|~$10          |
|**Total**                    |**~$15/month**|

-----

## Data Flow

```
External Sources
      │
      ▼
[Ingestion Layer]
Airbyte / Python scripts
      │
      ▼
[Raw Storage]
Cloudflare R2 — Parquet files
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
[Visualization Layer]
Metabase
```

-----

## Conventions

### Naming

- Tables: `snake_case`
- dbt models: prefixed by layer (`stg_`, `int_`, `fct_`, `dim_`)
- S3 paths: `s3://bucket/raw/{source}/{entity}/year={yyyy}/month={mm}/day={dd}/`

### Data Quality

- dbt native tests (`not_null`, `unique`, `accepted_values`) on all staging models
- At least one freshness test per source
- All failures block the pipeline in CI

### Documentation

- Every dbt model must have a description in `schema.yml`
- Architecture decisions documented as ADRs in `docs/decisions/`

-----

## Tools Not Used (and Why)

|Tool              |Reason skipped                                      |
|------------------|----------------------------------------------------|
|Apache Kafka      |Overkill without real streaming requirements        |
|Databricks        |High cost and operational complexity for small teams|
|Amazon Redshift   |Fixed instance cost, not suited for early stage     |
|DataHub / Atlan   |High maintenance overhead, premature optimization   |
|Tableau / Power BI|License cost not justified at this stage            |

-----

## Migration Triggers

These are the signals to move from Phase 1 to Phase 2:

- Query runtime on DuckDB consistently exceeds 5 minutes
- Raw data volume surpasses 50 GB
- More than 10 active pipelines in production
- A second data engineer joins the team
- Stakeholders require SLA guarantees on dashboard freshness

-----

## References

- [dbt Documentation](https://docs.getdbt.com)
- [DuckDB Documentation](https://duckdb.org/docs)
- [Airbyte Documentation](https://docs.airbyte.com)
- [Cloudflare R2 Pricing](https://developers.cloudflare.com/r2/pricing)
- [Metabase Documentation](https://www.metabase.com/docs)
