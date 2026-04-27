# Setup Manual

End-to-end walkthrough to bring up the full stack **assuming raw data is already in S3** at `s3://${S3_BUCKET}/raw/raw_events/year=*/month=*/day=*/`.

If you also need to generate and upload synthetic data first, run `./ingestion/scripts/push_to_s3.sh` once before starting — see [README → Quick Start](../README.md#quick-start).

For architecture rationale, see [`architecture.md`](architecture.md). For the layer-by-layer deep dives, see [`ingestion.md`](ingestion.md), [`orchestration.md`](orchestration.md), and [`evolution-triggers.md`](evolution-triggers.md).

---

## 0. Prerequisites

| Tool | Version | Why |
|---|---|---|
| [uv](https://docs.astral.sh/uv/) | latest | Manages Python 3.11+ and dependencies |
| AWS CLI | v2 | Reading from S3 |
| Git | any | Cloning |

You'll also need:

- **An S3 bucket** containing raw Parquet under `raw/raw_events/year=*/month=*/day=*/raw_events_<source>_<entity>_*.parquet`. The macro that reads it is in [`transformation/dbt/macros/raw_events.sql`](../transformation/dbt/macros/raw_events.sql).
- **AWS credentials** with read access to that bucket (and write access if you want dbt to round-trip `prod.duckdb` to `s3://${S3_BUCKET}/state/prod.duckdb`).

---

## 1. Clone and configure

```bash
git clone https://github.com/andrefsmelo/modern-data-stack-starter.git
cd modern-data-stack-starter

cp .env.example .env
```

Edit `.env` and set at minimum:

```bash
BUCKET=acme-data-prod          # used by ingestion scripts
S3_BUCKET=acme-data-prod       # used by dbt (read by raw_events macro)
S3_RAW_PREFIX=raw              # default — only change if your layout differs
AWS_REGION=eu-west-1
AWS_ACCESS_KEY_ID=AKIA...      # or leave unset and use AWS_PROFILE
AWS_SECRET_ACCESS_KEY=...
```

Variable reference: [README → Configuration](../README.md#configuration). All secrets stay local — never commit `.env`.

---

## 2. Python environment

```bash
uv venv
source .venv/bin/activate
uv pip install dbt-duckdb
```

`uv venv` creates `.venv/` using the first compatible Python it finds (or downloads one if needed). That's the only Python dep needed when raw data is already in S3 — the data generator deps (`faker`, `pandas`, `pyarrow`) are only required for ingestion.

---

## 3. Verify S3 raw data

```bash
set -a; source .env; set +a
aws s3 ls "s3://${S3_BUCKET}/raw/raw_events/" --recursive | head
```

You should see files matching `raw_events_<source>_<entity>_<date>.parquet`. If this is empty, either run the ingestion script (`./ingestion/scripts/push_to_s3.sh`) or upload your own raw data to that prefix before continuing.

---

## 4. Build the warehouse with dbt

```bash
cd transformation/dbt
set -a; source ../../.env; set +a; unset AWS_PROFILE

DBT_DUCKDB_PATH=prod.duckdb dbt build --profiles-dir . --target prod
```

`dbt build` runs models + tests in dependency order. You'll get a `prod.duckdb` file in `transformation/dbt/` containing the staging views, intermediate views, and marts (facts + dimensions).

**Why `unset AWS_PROFILE`:** the DuckDB httpfs extension uses `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` directly. If `AWS_PROFILE` is set, it can shadow those and break S3 reads.

To rebuild against a fresh state, delete the file first:

```bash
rm prod.duckdb && DBT_DUCKDB_PATH=prod.duckdb dbt build --profiles-dir . --target prod
```

---

## 5. Orchestration (GitHub Actions)

The workflows live in [`.github/workflows/`](../.github/workflows/) — see [`orchestration/README.md`](../orchestration/README.md) for the layout and conventions.

In your repo's GitHub settings (**Settings → Secrets and variables → Actions**), set:

**Variables**
- `S3_BUCKET` — e.g. `acme-data-prod`
- `AWS_REGION` — e.g. `eu-west-1`

**Secrets**
- `AWS_ACCESS_KEY_ID`
- `AWS_SECRET_ACCESS_KEY`
- `SLACK_WEBHOOK_URL` *(optional — failure notifications no-op when unset)*

Then push to GitHub. The `dbt-build` workflow runs on cron `0 */6 * * *` and round-trips `prod.duckdb` through `s3://${S3_BUCKET}/state/prod.duckdb`. The `ingest` workflow is manual-only — trigger from the **Actions** tab when you want to refresh the synthetic data.

To kick off the first scheduled run immediately:

**Actions** tab → **dbt-build** → **Run workflow** → leave defaults → **Run**.

---

## 6. Refresh loop (after first build)

Once orchestration is wired up, the steady-state loop is:

```
GH Actions cron  →  dbt-build  →  prod.duckdb to S3
                                       ↓
                                  pull locally  →  query with duckdb CLI
```

To pull the latest `prod.duckdb` produced by CI:

```bash
aws s3 cp "s3://${S3_BUCKET}/state/prod.duckdb" transformation/dbt/prod.duckdb
```

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `IO Error: Connection error for HTTP HEAD` during `dbt run` | DuckDB can't reach S3 | Check `AWS_REGION`; `unset AWS_PROFILE`; verify keys with `aws s3 ls` |
| `No files found` from the `read_raw_events` macro | Wrong `S3_BUCKET` or `S3_RAW_PREFIX`, or empty prefix | Re-run the verification in [step 3](#3-verify-s3-raw-data) |
| GH Actions `dbt-build` fails on first run with "no such file" | Expected — empty `state/` bucket | The workflow handles this, builds from scratch, then uploads |
| `dbt build` works locally but fails in CI | Missing repo Variables/Secrets | Re-check [step 5](#5-orchestration-github-actions) |

For deeper debugging see the per-layer docs linked at the top of this file.
