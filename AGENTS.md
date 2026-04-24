# AGENTS.md

This file helps AI agents navigate the repository quickly.

## Architecture & Design

All architecture decisions, phase plans, cost estimates, data flow diagrams, tool rationale, naming conventions, and migration triggers are documented in:

**[docs/architecture.md](docs/architecture.md)**

## Project Layout

```
modern-data-stack-starter/
├── ingestion/            # Airbyte configs and custom Python ingestion scripts
├── transformation/       # dbt project (models, tests, schema.yml)
├── orchestration/        # GitHub Actions workflows
├── visualization/        # Metabase dashboard exports and configs
├── docs/
│   ├── architecture.md   # ← full architecture document (start here)
│   └── decisions/        # Architecture Decision Records (ADRs)
└── README.md             # Quick-start and setup instructions
```

## Git Workflow

- **Never merge directly to main.** Always push to a feature branch and create a PR so the owner can review and approve it.

## Key Facts

- **Current phase:** Phase 1 (Bootstrap) — Airbyte + Cloudflare R2 + dbt Core + DuckDB + Metabase
- **Target cost:** ~$15/month
- **dbt layer prefixes:** `stg_` staging, `int_` intermediate, `fct_` facts, `dim_` dimensions
- **Storage path pattern:** `s3://bucket/raw/{source}/{entity}/year={yyyy}/month={mm}/day={dd}/`
