# Visualization (Metabase)

Self-hosted Metabase connected to the `prod.duckdb` file produced by dbt.

## Quick Start

```bash
# 1. Build prod.duckdb and start Metabase
./visualization/setup.sh

# 2. (Optional) Provision dashboards via API
python visualization/provision_dashboards.py

# 3. Open http://localhost:3000
#    Login: admin@modern-data-stack.local / Metabase123!
```

## Architecture

Per [ADR-0001](../../docs/decisions/0001-duckdb-execution.md), Metabase reads a **read-only copy** of `prod.duckdb`. The file is mounted into the container from the host path.

```
dbt run (GitHub Actions)  →  prod.duckdb  →  S3 (state backup)
                                    ↘
                              Metabase (Docker, read-only mount)
```

## Refreshing Data

```bash
# Rebuild prod.duckdb from S3 sources
cd transformation/dbt
set -a; source ../../.env; set +a; unset AWS_PROFILE
DBT_DUCKDB_PATH=prod.duckdb ../../.venv/bin/dbt run --profiles-dir . --target prod

# Restart Metabase to pick up the refreshed file
docker compose restart metabase
```

For production, a GitHub Actions workflow handles this automatically after each dbt run.

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `MB_PORT` | `3000` | Host port for Metabase UI |
| `MB_USER` | `admin@modern-data-stack.local` | Metabase admin email |
| `MB_PASS` | `Metabase123!` | Metabase admin password |
| `DUCKDB_PATH` | `./transformation/dbt/prod.duckdb` | Path to DuckDB file (mounted read-only) |
| `DB_NAME` | `Modern Data Stack - Prod` | Metabase database display name |

## Files

| File | Purpose |
|---|---|
| `setup.sh` | Build DuckDB, start Metabase, configure connection |
| `provision_dashboards.py` | Create dashboards and questions via Metabase API |
| `export-dashboards.sh` | Export dashboards from Metabase to JSON (for backup) |
| `dashboards/` | Imported dashboard JSON files |

## DuckDB Driver

Metabase does not ship with a DuckDB driver. `setup.sh` auto-downloads the community driver JAR to `plugins/` (gitignored). See: https://github.com/AlexR2D2/metabase-duckdb-driver