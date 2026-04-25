# modern-data-stack-starter

A lightweight, cost-effective data platform blueprint for companies of up to ~50 employees. Designed to bootstrap in days, run for ~$30/month, and grow without throwing the foundation away.

For the full architecture rationale, layered phase plans, and tool decisions see [docs/architecture.md](docs/architecture.md). For the ingestion-tool deep dive (Airbyte vs. dlt vs. Meltano vs. Fivetran vs. CDC), see [docs/ingestion.md](docs/ingestion.md). For the operational signals that should drive a change, see [docs/evolution-triggers.md](docs/evolution-triggers.md).

-----

## Who this is for

A company with up to ~50 employees and one (or one-and-a-half) data engineers, who needs:

- A working analytics stack within a week, not a quarter
- A monthly bill measured in tens of dollars, not thousands
- An exit ramp at every layer — open formats and portable tools, no proprietary lock-in
- A clear answer to "what do we change first when we outgrow this?"

If you have > 50 employees, > 5 data engineers, or you need real-time pipelines, this blueprint is the wrong starting point — but most of the conventions still apply.

-----

## The default stack

| Layer          | Tool                              | Why                                                |
|----------------|-----------------------------------|----------------------------------------------------|
| Ingestion      | dlt (default) or Airbyte (if UI)  | See [docs/ingestion.md](docs/ingestion.md) for the choice |
| Storage        | Amazon S3 (Parquet, Iceberg-ready)| Open format, mature ecosystem, cheap at small scale|
| Transformation | dbt Core + DuckDB                 | No license cost, handles 100s of GB on a single node|
| Orchestration  | GitHub Actions (cron)             | No new infrastructure to operate                   |
| Visualization  | Metabase (self-hosted)            | Free, easy to use, self-contained                  |
| Observability  | GitHub Actions → Slack alerts     | Surfaces failures where the team already lives     |

**Cost target**: ~$30–35/month. Drops to ~$10/month if you skip Airbyte and use dlt-in-CI for ingestion.

-----

## Prerequisites

- Docker and Docker Compose (only if running Airbyte or Metabase locally)
- Python 3.11+
- `dbt-duckdb` (`pip install dbt-duckdb`)
- An Amazon S3 bucket (or any S3-compatible storage)
- AWS credentials with read/write access to the bucket

-----

## Quick Start

```bash
git clone https://github.com/your-org/modern-data-stack-starter.git
cd modern-data-stack-starter

# Set up Python environment
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Configure credentials
cp .env.example .env
# edit .env with your AWS keys and bucket name

# Option A — ingest with dlt (recommended default)
python ingestion/dlt_pipelines/example.py

# Option B — ingest with Airbyte (only if you want a UI)
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
│   ├── dlt_pipelines/        # dlt Python pipelines (default)
│   ├── airbyte/              # Airbyte connection configs (optional)
│   └── scripts/              # Custom Python scripts for exotic sources
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
│   ├── ingestion.md          # Ingestion tool landscape and decision matrix
│   ├── evolution-triggers.md # Per-layer signals to scale
│   └── decisions/            # Architecture Decision Records (ADRs)
└── README.md
```

-----

## Configuration

Copy `.env.example` to `.env` and fill in your credentials:

```bash
cp .env.example .env
```

| Variable               | Description                            |
|------------------------|----------------------------------------|
| `AWS_ACCESS_KEY_ID`    | AWS access key with S3 permissions     |
| `AWS_SECRET_ACCESS_KEY`| AWS secret key                         |
| `AWS_REGION`           | Bucket region (e.g. `us-east-1`)       |
| `S3_BUCKET`            | Target bucket name (e.g. `acme-data-prod`)|
| `DBT_TARGET`           | `dev` (local) or `prod` (CI)           |

In production, these live as **GitHub Actions Secrets** — never commit a populated `.env`.

-----

## Running in CI

Transformations run automatically via GitHub Actions on a cron schedule. The workflow downloads `prod.duckdb` from S3, runs `dbt build`, and uploads the updated file back. Concurrency is capped at one to prevent concurrent writers. See [docs/decisions/0001-duckdb-execution.md](docs/decisions/0001-duckdb-execution.md) for the full rationale.

-----

## When to upgrade

This stack is designed to last 12–18 months for a company growing toward ~50 employees. Beyond that, **upgrade the layer that hurts, not the whole stack**. The full per-layer playbook is in [docs/evolution-triggers.md](docs/evolution-triggers.md); the headline scenarios are below.

### Scenario A — "We have a lot more data" (volume-driven upgrade)

**Symptoms**: `dbt run` consistently > 5 min on the slowest model after tuning, or raw S3 volume > 200 GB, or analysts blocked waiting for the single-writer DuckDB lock.

**Move**: keep S3 + Iceberg for storage; move the **compute layer** to **BigQuery on-demand** or **Snowflake X-Small**. Keep dbt — only the adapter changes (`dbt-duckdb` → `dbt-bigquery` or `dbt-snowflake`). Expect the bill to jump from ~$30/mo to **~$100–300/mo** depending on query patterns.

Adopt **Iceberg** on top of S3 *before* the warehouse migration — it lets DuckDB and BigQuery/Snowflake both read the same raw layer, which makes the migration incremental rather than a flag-day cutover.

### Scenario B — "We have a lot more sources" (ingestion-driven upgrade)

**Symptoms**: > 10 active ingestion sources, OR the self-hosted Airbyte VM is OOM-ing weekly, OR a non-engineer team (marketing, finance) wants to add their own SaaS connections without filing a ticket.

**Move**: upgrade the **ingestion layer** only. Two options depending on team preference:

- **(a) Airbyte Cloud** — managed, eliminates the self-hosted VM. Best when the team would rather pay than operate.
- **(b) Dedicated Airbyte VM** (8 GB RAM, ~$40/mo) with proper monitoring and connector pinning. Best when cost matters more than ops time.

If most of your sources are simple SaaS APIs and the team is engineer-led, evaluate **Meltano** before either Airbyte option — it covers the same connector library without the JVM operational cost. See [docs/ingestion.md](docs/ingestion.md) for the full comparison.

If a single source produces > 10 GB/day, **don't scale Airbyte** — peel that one source off and move it to a dedicated dlt or Sling job. Airbyte's row-by-row architecture is wrong for bulk extracts.

### Scenario C — "Stakeholders need fresher data" (latency-driven upgrade)

**Symptoms**: a product owner asks for sub-hour freshness from an operational database; finance wants real-time revenue dashboards.

**Move**: this is **out of scope for Phase 1**. Adopting CDC introduces a different operational discipline (Kafka or DMS, schema-evolution on the wire, idempotent consumers). Evaluate **AWS DMS** (managed, AWS-only) or **Estuary Flow** (managed, multi-cloud) before reaching for **Debezium + Kafka** (self-operated). Update the architecture doc's non-goals before adopting.

### Scenario D — "One source is a PDF or photo" (document / OCR-driven addition)

**Symptoms**: finance receives PDF invoices from vendors, ops scans paper forms, sales attaches contracts in PDF, the team uploads receipt photos, or an external partner drops scanned documents into a shared folder. Whatever the source, the data lives inside a document and needs **text + field extraction** before it can become a row.

**Move**: add a **document extraction step** as a new ingestion job — don't try to bend Airbyte or dlt to do this. The flow lands the original file in `s3://{bucket}/raw/documents/...`, runs an extraction job, and writes structured Parquet to `s3://{bucket}/raw/documents_extracted/...`. dbt then treats the extracted output as a normal source.

Pick the extractor by document profile:

- **Variable layouts** (50 vendors send invoices in 50 formats, contracts from many counterparties): **LLM extraction** with **Claude** or **GPT-4o** using a structured-output schema. Cheapest path to a working pipeline; ~$0.01–0.05 per page; no per-template rules to maintain.
- **Fixed templates** (your own forms, one vendor's invoice format, monthly reports from a single source): **AWS Textract** or **Google Document AI**. Cheaper per page at volume, deterministic, well-supported on AWS/GCP.
- **Document type matches a Document AI specialized parser** (W-2, receipt, ID card, bank statement): **Google Document AI** specialized parser — returns clean structured fields out of the box.
- **Sensitive / on-prem only** or **> 100k pages/month**: **PaddleOCR** or **docTR** self-hosted. Removes per-page cloud cost; needs a GPU and someone to operate the pipeline.

Always keep the original document in S3 — re-extraction is the right answer when the schema or extractor changes. Validate every extraction with dbt tests (`not_null` on key fields, range checks on totals); non-deterministic extractors slip occasionally and dbt is the right place to catch it. See [docs/ingestion.md](docs/ingestion.md#unstructured--document-extraction-ocr--document-ai) for the full per-tool comparison.

-----

## Contributing

1. Branch off `main`
2. Add or modify dbt models under `transformation/models/`
3. Ensure `dbt test` passes locally before opening a PR
4. Document any new model in its `schema.yml`
5. For new ingestion sources, document the tool choice and rationale per [docs/ingestion.md](docs/ingestion.md)
