# AGENTS.md

This file helps AI agents navigate the repository quickly.

## Architecture & Design

- **[docs/architecture.md](docs/architecture.md)** — full architecture: phase plans, layers, cost estimates, data flow, conventions, naming, secrets, environments, data quality severities.
- **[docs/ingestion.md](docs/ingestion.md)** — ingestion-tool landscape (managed, OSS, code-first, CDC), pros/cons, and the decision matrix for picking one. Use when reasoning about ingestion choices.
- **[docs/evolution-triggers.md](docs/evolution-triggers.md)** — per-layer operational signals and the recommended next move when each fires (use this when reasoning about scaling decisions).
- **[docs/decisions/](docs/decisions/)** — Architecture Decision Records. Start with `0001-duckdb-execution.md`.

## Project Layout

```
modern-data-stack-starter/
├── ingestion/            # Airbyte configs, dlt pipelines, custom Python scripts
├── transformation/       # dbt project (models, tests, schema.yml)
├── orchestration/        # GitHub Actions workflows (cron schedules, dbt jobs)
├── visualization/        # Metabase dashboard exports and configs
├── docs/
│   ├── architecture.md       # ← full architecture (start here)
│   ├── ingestion.md          # ← ingestion-tool landscape and decision matrix
│   ├── evolution-triggers.md # ← when to scale each layer
│   └── decisions/            # Architecture Decision Records (ADRs)
└── README.md             # Quick-start and setup instructions
```

## Git Workflow

- **Never merge directly to main.** Always push to a feature branch and create a PR so the owner can review and approve it.

## Key Facts

- **Current phase:** Phase 1 (Bootstrap) — Airbyte/dlt + Amazon S3 + dbt Core + DuckDB + Metabase
- **Target cost:** ~$30-35/month (≈$10/month if Airbyte is replaced by dlt in GitHub Actions)
- **Storage:** Amazon S3, Parquet files in an Iceberg-ready layout
- **dbt execution:** GitHub Actions runners; `prod.duckdb` round-trips through S3 (see ADR-0001)
- **dbt layer prefixes:** `stg_` staging, `int_` intermediate, `fct_` facts, `dim_` dimensions
- **Storage path pattern:** `s3://{bucket}/raw/{source}/{entity}/year={yyyy}/month={mm}/day={dd}/`
- **Bucket naming:** `{org}-data-{env}` (e.g. `acme-data-prod`, `acme-data-dev`)
- **Secrets:** GitHub Actions Secrets only; dbt reads via `env_var()`
- **Test severities:** `error` blocks the pipeline (PK uniqueness, not-null on join keys); `warn` notifies but does not block.
- **Ingestion default:** dlt (engineering-led teams) or Airbyte (when non-engineers add sources). Full landscape and decision matrix in `docs/ingestion.md`.
