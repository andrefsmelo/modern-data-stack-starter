# Orchestration

The actual workflow files live in [`.github/workflows/`](../.github/workflows/) at the repo root — that's the only path GitHub Actions recognizes. This directory exists to document the orchestration layer and host any helper scripts that workflows call.

For the rationale, pricing math, and escape hatches (Lambda, Fargate, Modal, Cloud Run), see [`docs/orchestration.md`](../docs/orchestration.md).

## Workflows

| File | Trigger | Purpose |
|---|---|---|
| [`.github/workflows/ingest.yml`](../.github/workflows/ingest.yml) | manual (`workflow_dispatch`) | Generates synthetic data and pushes to S3. Manual-only because the generator is seeded — a cron would just regenerate the same data. Swap the body for `dlt`/Airbyte and add `schedule:` for a real source. |
| [`.github/workflows/dbt-build.yml`](../.github/workflows/dbt-build.yml) | cron `0 */6 * * *` + manual | Downloads `prod.duckdb` from S3, runs `dbt build`, uploads it back. Concurrency capped to 1 — see [ADR-0001](../docs/decisions/0001-duckdb-execution.md). |

## Required configuration

Set these in the repo's GitHub Actions settings (Settings → Secrets and variables → Actions):

**Secrets**
- `AWS_ACCESS_KEY_ID`
- `AWS_SECRET_ACCESS_KEY`
- `SLACK_WEBHOOK_URL` *(optional — failure notifications no-op if unset)*

**Variables**
- `S3_BUCKET` — e.g. `acme-data-prod`
- `AWS_REGION` — e.g. `eu-west-1`

## State convention

`dbt-build.yml` stores the production DuckDB file at `s3://${S3_BUCKET}/state/prod.duckdb`. The first run builds from scratch when the key is absent.

## Conventions enforced in every workflow

Per [`docs/orchestration.md`](../docs/orchestration.md#operational-conventions):

- Pinned action versions (`@v4`, never `@main`)
- `timeout-minutes` set on every job
- `concurrency.group` to prevent overlapping runs racing on shared state
- `workflow_dispatch` on every workflow for manual backfill / debugging
- Slack notification on failure (when `SLACK_WEBHOOK_URL` is set)
