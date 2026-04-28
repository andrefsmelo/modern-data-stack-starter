# Setup Guide

Welcome! This guide walks you through getting the stack running on your machine. It's written so you can follow along even if you've never touched dbt, DuckDB, or S3 before.

## Pick your path

There are two ways to run this project. **Start with Path A** unless you specifically need cloud storage.

| | Path A — Local demo | Path B — Full S3-backed stack |
|---|---|---|
| **Best for** | Trying the natural-language CLI, exploring the marts, demoing the project | Running the orchestrated cron pipeline, sharing `prod.duckdb` across machines |
| **Time** | ~5 minutes | ~20 minutes |
| **You need** | Python 3.11+, an Anthropic API key | Path A's prereqs **plus** an AWS account, an S3 bucket, AWS credentials |
| **Data source** | Synthetic data generated locally | Synthetic data uploaded to S3 (or your own raw Parquet) |
| **Where `prod.duckdb` lives** | `transformation/dbt/prod.duckdb` on your laptop | Same, plus a copy in `s3://${S3_BUCKET}/state/prod.duckdb` |

The two paths share the first three steps; Path B adds steps 4-7.

---

## Step 0 — Install the prerequisites

You'll need:

- **[uv](https://docs.astral.sh/uv/getting-started/installation/)** — manages Python 3.11+ and dependencies. One-line install on macOS/Linux:
  ```bash
  curl -LsSf https://astral.sh/uv/install.sh | sh
  ```
- **Git** — to clone the repo.
- **An [Anthropic API key](https://console.anthropic.com/)** — for the natural-language CLI. Free credits are enough to run all the examples.

If you're following **Path B**, you'll additionally need:

- **The [AWS CLI v2](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html)**.
- **An S3 bucket** you can read and write to (e.g. `acme-data-prod`). If you don't have one yet: AWS Console → S3 → Create bucket → leave defaults → done.
- **AWS credentials** with read/write access to that bucket — either an IAM user's access key pair, or a configured `AWS_PROFILE`.

> **Sanity check.** Run `uv --version` and `git --version`. Both should print a version number. For Path B, also run `aws sts get-caller-identity` and confirm it returns your AWS account info.

---

## Step 1 — Clone and set up Python

```bash
git clone https://github.com/andrefsmelo/modern-data-stack-starter.git
cd modern-data-stack-starter

uv venv
source .venv/bin/activate
uv pip install dbt-duckdb pandas pyarrow faker boto3 numpy anthropic duckdb pyyaml
```

`uv venv` creates `.venv/` using a compatible Python (it'll download Python 3.11 if you don't have one). The `pip install` line covers everything for both paths — data generation, dbt, the natural-language CLI.

> **Sanity check.** `which python` should now point inside `.venv/`. `dbt --version` should print "Core: 1.x.x" and list the `duckdb` adapter.

---

## Step 2 — Configure `.env`

```bash
cp .env.example .env
```

Open `.env` in your editor. **For Path A**, you only need one variable:

```bash
ANTHROPIC_API_KEY=sk-ant-...
```

**For Path B**, set these too:

```bash
BUCKET=acme-data-prod          # used by the ingestion scripts
S3_BUCKET=acme-data-prod       # used by dbt (read by the raw_events macro)
S3_RAW_PREFIX=raw              # default — only change if your S3 layout differs
AWS_REGION=eu-west-1
AWS_ACCESS_KEY_ID=AKIA...      # or leave unset and use AWS_PROFILE
AWS_SECRET_ACCESS_KEY=...
```

> **Why two bucket variables?** `BUCKET` is what the Bash ingestion scripts read; `S3_BUCKET` is what the dbt `raw_events` macro reads. They almost always have the same value. Keeping them separate makes it easy to point dbt at one bucket and the uploader at another (e.g. for a dev/prod split).

> **Never commit `.env`.** It's already gitignored. Secrets stay on your machine.

---

## Step 3 — Generate the synthetic data

```bash
python ingestion/scripts/generate_dummy_data.py
```

This creates a deliberately-dirty fintech dataset under `./data/`: ~120 customers, three months of credit facilities, drawdowns, repayments, FX transactions, and account balances, plus ~2-5% intentionally orphaned rows. Full spec: [`test-data-specification.md`](test-data-specification.md).

> **Sanity check.** `ls data/raw/raw_events/` should show partitioned directories like `year=2026/month=01/day=01/`.

### If you're on Path A — skip ahead to [Step 4A](#step-4a--build-the-warehouse-locally-path-a).
### If you're on Path B — continue with [Step 4B](#step-4b--upload-the-data-to-s3-path-b).

---

## Step 4A — Build the warehouse locally (Path A)

```bash
cd transformation/dbt
dbt build
```

`dbt build` runs every model and every test in dependency order. You'll get a `prod.duckdb` file in `transformation/dbt/` that contains:

- **Staging views** (`stg_*`) — typed, renamed copies of the raw tables.
- **Intermediate views** (`int_*`) — FX normalisation, repayment-schedule expansion, ARR-per-customer, facility utilisation.
- **Marts** — `fct_drawdowns`, `fct_repayments`, `fct_fx_transactions`, `dim_customers`, `dim_credit_facilities`.

> **Sanity check.** The last line should read `Completed successfully` with a count of passed tests. To peek at the warehouse:
> ```bash
> duckdb prod.duckdb "SELECT COUNT(*) FROM main_marts.dim_customers"
> ```
> You should see ~120.

You're done with Path A's data setup. **Jump to [Step 8 — Ask the warehouse a question](#step-8--ask-the-warehouse-a-question).**

---

## Step 4B — Upload the data to S3 (Path B)

```bash
./ingestion/scripts/push_to_s3.sh
```

This uploads everything under `data/raw/` to `s3://${S3_BUCKET}/raw/`.

> **Sanity check.**
> ```bash
> aws s3 ls "s3://${S3_BUCKET}/raw/raw_events/" --recursive | head
> ```
> You should see files matching `raw_events_<source>_<entity>_<date>.parquet`.

---

## Step 5B — Build the warehouse from S3 (Path B)

```bash
cd transformation/dbt
set -a; source ../../.env; set +a; unset AWS_PROFILE

DBT_DUCKDB_PATH=prod.duckdb dbt build --profiles-dir . --target prod
```

> **Why `unset AWS_PROFILE`?** DuckDB's `httpfs` extension reads `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` directly. If `AWS_PROFILE` is also set, it can shadow the env vars and break S3 reads. This is the single most common Path B gotcha.

To rebuild against a fresh state, delete the file first:

```bash
rm prod.duckdb && DBT_DUCKDB_PATH=prod.duckdb dbt build --profiles-dir . --target prod
```

> **Sanity check.** Same as Step 4A — last line says `Completed successfully`, and `duckdb prod.duckdb "SELECT COUNT(*) FROM main_marts.dim_customers"` returns ~120.

---

## Step 6B — Wire up GitHub Actions (optional, Path B)

The workflows in [`.github/workflows/`](../.github/workflows/) run dbt on a 6-hour cron and round-trip `prod.duckdb` through `s3://${S3_BUCKET}/state/prod.duckdb`. Authoritative configuration reference (what each Variable / Secret is for, the IAM policy, and the error → fix mapping) is in [`orchestration/README.md`](../orchestration/README.md#required-configuration).

Short version — set in your repo's GitHub settings (**Settings → Secrets and variables → Actions**):

| Tab        | Name                    | Required | Value                            |
|------------|-------------------------|----------|----------------------------------|
| Variables  | `S3_BUCKET`             | yes      | e.g. `acme-data-prod`            |
| Variables  | `AWS_REGION`            | yes      | e.g. `eu-west-1`                 |
| Secrets    | `AWS_ACCESS_KEY_ID`     | yes      | IAM key with the [policy in the orchestration doc](../orchestration/README.md#iam-policy-the-aws-key-needs) |
| Secrets    | `AWS_SECRET_ACCESS_KEY` | yes      |                                  |
| Secrets    | `SLACK_WEBHOOK_URL`     | no       | failure-notification webhook     |

Don't put a key in the wrong tab — Variables are visible in workflow logs.

Then push your repo to GitHub. To trigger the first run immediately:

> **Actions** tab → **dbt-build** → **Run workflow** → leave defaults → **Run**.

If it fails, the [common failure modes table](../orchestration/README.md#common-failure-modes-error--fix) maps each error message to the missing config.

---

## Step 7B — The steady-state refresh loop (Path B)

Once orchestration is wired up:

```
GH Actions cron  →  dbt-build  →  prod.duckdb to S3
                                       ↓
                                  pull locally  →  query with the CLI or duckdb
```

To pull the latest `prod.duckdb` produced by CI:

```bash
aws s3 cp "s3://${S3_BUCKET}/state/prod.duckdb" transformation/dbt/prod.duckdb
```

---

## Step 8 — Ask the warehouse a question

Both paths converge here.

```bash
cd ..   # back to the repo root, if you're still inside transformation/dbt
export ANTHROPIC_API_KEY=sk-ant-...   # if you didn't put it in .env

python analytics/query.py "Top 10 customers by ARR"
python analytics/query.py --show-sql "Drawdowns by month over the last 6 months"
```

`--show-sql` prints the generated SQL before the result — handy for sanity-checking and for learning the schema.

For more example questions, design notes, costs, and limits: [`analytics/README.md`](../analytics/README.md). For a guided tour of the marts: [`marts.md`](marts.md).

---

## Step 9 — Explore further

Two more ways to consume `prod.duckdb`:

```bash
# A. Browse the schema and lineage in your browser
cd transformation/dbt && dbt docs generate && dbt docs serve

# B. Open it in any DuckDB client
duckdb transformation/dbt/prod.duckdb
```

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `IO Error: Connection error for HTTP HEAD` during `dbt build` | DuckDB can't reach S3 | Check `AWS_REGION`, run `unset AWS_PROFILE`, verify keys with `aws s3 ls` |
| `No files found` from the `read_raw_events` macro | Wrong `S3_BUCKET` or `S3_RAW_PREFIX`, or empty prefix | Re-run the verification in [Step 4B](#step-4b--upload-the-data-to-s3-path-b) |
| `dbt: command not found` | Virtualenv not activated | `source .venv/bin/activate` from the repo root |
| `ANTHROPIC_API_KEY environment variable not set` | Key not exported | `export ANTHROPIC_API_KEY=sk-ant-...` or add it to `.env` and re-source it |
| `python: can't open file 'analytics/query.py'` | Wrong working directory | `cd` back to the repo root |
| GitHub Actions `dbt-build` fails on the first run with "no such file" | Expected — empty `state/` prefix | The workflow handles this, builds from scratch, then uploads |
| `dbt build` works locally but fails in CI | Missing repo Variables/Secrets | Re-check [Step 6B](#step-6b--wire-up-github-actions-optional-path-b) |

For deeper debugging, see the per-layer docs: [`architecture.md`](architecture.md), [`ingestion.md`](ingestion.md), [`orchestration.md`](orchestration.md), [`evolution-triggers.md`](evolution-triggers.md).
