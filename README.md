# modern-data-stack-starter

A lightweight, cost-effective data platform blueprint for early-stage startups (~$15/month).

For the full architecture rationale, phase plans, and tool decisions see [docs/architecture.md](docs/architecture.md).

-----

## Prerequisites

- Docker and Docker Compose
- Python 3.11+
- `dbt-duckdb` (`pip install dbt-duckdb`)
- A Cloudflare R2 bucket (or any S3-compatible storage)

-----

## Quick Start

```bash
git clone https://github.com/your-org/modern-data-stack-starter.git
cd modern-data-stack-starter

# Set up Python environment
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Start Airbyte (self-hosted)
cd ingestion/airbyte && docker compose up -d

# Run dbt transformations
cd transformation
dbt deps
dbt run
dbt test
```

-----

## Project Structure

```
modern-data-stack-starter/
├── ingestion/
│   ├── airbyte/              # Airbyte connection configs
│   └── scripts/              # Custom Python ingestion scripts
├── transformation/
│   ├── dbt_project.yml
│   ├── models/
│   │   ├── staging/          # Raw → cleaned
│   │   ├── intermediate/     # Business logic
│   │   └── marts/            # Final analytical models
│   └── tests/
├── orchestration/
│   └── .github/workflows/    # GitHub Actions DAGs
├── visualization/
│   └── metabase/             # Dashboard exports / configs
├── docs/
│   ├── architecture.md       # Architecture, phases, cost, conventions
│   └── decisions/            # Architecture Decision Records (ADRs)
└── README.md
```

-----

## Configuration

Copy `.env.example` to `.env` and fill in your credentials:

```bash
cp .env.example .env
```

| Variable              | Description                        |
|-----------------------|------------------------------------|
| `R2_ACCOUNT_ID`       | Cloudflare R2 account ID           |
| `R2_ACCESS_KEY_ID`    | R2 access key                      |
| `R2_SECRET_ACCESS_KEY`| R2 secret key                      |
| `R2_BUCKET`           | Target bucket name                 |

-----

## Running in CI

Transformations run automatically via GitHub Actions on every push to `main`. See [orchestration/.github/workflows/](orchestration/.github/workflows/).

-----

## Contributing

1. Branch off `main`
2. Add or modify dbt models under `transformation/models/`
3. Ensure `dbt test` passes locally before opening a PR
4. Document any new model in its `schema.yml`
