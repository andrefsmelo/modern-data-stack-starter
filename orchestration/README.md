# Orchestration

The actual workflow files live in [`.github/workflows/`](../.github/workflows/) at the repo root — that's the only path GitHub Actions recognizes. This directory exists to document the orchestration layer and host any helper scripts that workflows call.

For the rationale, pricing math, and escape hatches (Lambda, Fargate, Modal, Cloud Run), see [`docs/orchestration.md`](../docs/orchestration.md).

## Workflows

| File | Trigger | Purpose |
|---|---|---|
| [`.github/workflows/ingest.yml`](../.github/workflows/ingest.yml) | manual (`workflow_dispatch`) | Generates synthetic data and pushes to S3. Manual-only because the generator is seeded — a cron would just regenerate the same data. Swap the body for `dlt`/Airbyte and add `schedule:` for a real source. |
| [`.github/workflows/dbt-build.yml`](../.github/workflows/dbt-build.yml) | cron `0 */6 * * *` + manual | Downloads `prod.duckdb` from S3, runs `dbt build`, runs `dbt source freshness`, exports each mart as a Parquet file to `s3://${S3_BUCKET}/marts/<table>/<table>.parquet` (so non-DuckDB engines can read them — Glue/Athena setup in [`transformation/exports/README.md`](../transformation/exports/README.md#consumer-registering-the-marts-in-aws-glue-one-time-per-aws-account--region)), then uploads `prod.duckdb` back. Concurrency capped to 1 — see [ADR-0001](../docs/decisions/0001-duckdb-execution.md). |

## Slack Observability

Both workflows send a Slack notification on **every run** (success or failure) via [`scripts/notify_slack.py`](scripts/notify_slack.py). The notification is skipped if `SLACK_WEBHOOK_URL` is unset.

### Message content

| Workflow | What's reported |
|---|---|
| `dbt-build` | Status, run link, duration, model/test pass/fail counts, freshness results |
| `ingest` | Status, run link, duration |

### Severity routing (dbt)

- `severity: error` test failures → pipeline fails → Slack shows red/failure message
- `severity: warn` test failures → pipeline succeeds → Slack shows green/success with warning details
- Source freshness failures → reported in the Slack message but do not block the pipeline

### Setup

1. Create a Slack App with an incoming webhook in your workspace.
2. Add `SLACK_WEBHOOK_URL` as a **GitHub Actions Secret** (Settings → Secrets → New repository secret).
3. Run a workflow manually — you should see a message in the channel.

## Required configuration

Set these in the repo: **Settings → Secrets and variables → Actions**.

The "Variables" tab is for non-sensitive values referenced as `${{ vars.X }}`; the "Secrets" tab is for credentials referenced as `${{ secrets.X }}`. Don't put a key ID in the wrong tab — Variables are visible in workflow logs.

### Variables (Settings → Variables → New repository variable)

| Name         | Used by                                       | Example          | Required for      | Symptom if unset / empty                                                                  |
|--------------|-----------------------------------------------|------------------|-------------------|-------------------------------------------------------------------------------------------|
| `S3_BUCKET`  | both workflows; `dbt` `read_raw_events` macro | `acme-data-prod` | every dbt run     | `IO Error: URL needs to contain a bucket name` from DuckDB on the first staging model     |
| `AWS_REGION` | both workflows; profiles.yml httpfs settings  | `eu-west-1`      | every dbt run     | `S3 region not found` or unexpected redirect responses from DuckDB                        |

### Secrets (Settings → Secrets → New repository secret)

| Name                    | Used by               | Required?  | Symptom if unset                                                                              |
|-------------------------|-----------------------|------------|-----------------------------------------------------------------------------------------------|
| `AWS_ACCESS_KEY_ID`     | dbt-build, ingest     | required   | `HTTP 403 Forbidden ... AccessDenied ... No credentials are provided` from DuckDB httpfs      |
| `AWS_SECRET_ACCESS_KEY` | dbt-build, ingest     | required   | same as above                                                                                 |
| `SLACK_WEBHOOK_URL`     | dbt-build, ingest     | optional   | failure and success notifications are skipped; nothing else breaks                                     |

### IAM policy the AWS key needs

Minimum permissions on the bucket named in `S3_BUCKET`:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "ReadRawStateAndMarts",
      "Effect": "Allow",
      "Action": ["s3:GetObject", "s3:ListBucket"],
      "Resource": [
        "arn:aws:s3:::<bucket>",
        "arn:aws:s3:::<bucket>/raw/*",
        "arn:aws:s3:::<bucket>/state/*",
        "arn:aws:s3:::<bucket>/marts/*"
      ]
    },
    {
      "Sid": "WriteStateAndMarts",
      "Effect": "Allow",
      "Action": ["s3:PutObject"],
      "Resource": [
        "arn:aws:s3:::<bucket>/state/*",
        "arn:aws:s3:::<bucket>/marts/*"
      ]
    },
    {
      "Sid": "WriteRawForIngest",
      "Effect": "Allow",
      "Action": ["s3:PutObject"],
      "Resource": "arn:aws:s3:::<bucket>/raw/*"
    }
  ]
}
```

`WriteRawForIngest` is only needed by the `ingest` workflow (the synthetic-data uploader). Drop it once a real ingestion source replaces the stub.

### Quick check that everything is wired

After setting the four required entries, kick off **Actions → dbt-build → Run workflow** manually. The first staging model hitting S3 is the canary — if it succeeds, all four are correct. If it fails, the error message maps 1:1 to the tables above.

### Common failure modes (error → fix)

| Error message in CI                                                                       | Root cause                                       | Fix                                                                       |
|-------------------------------------------------------------------------------------------|--------------------------------------------------|---------------------------------------------------------------------------|
| `IO Error: URL needs to contain a bucket name`                                            | `S3_BUCKET` Variable unset or empty              | Set `vars.S3_BUCKET` (Variables tab)                                      |
| `HTTP 403 Forbidden ... AccessDenied ... No credentials are provided`                     | `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` Secrets unset, empty, or wrong | Set both Secrets (Secrets tab)                                            |
| `HTTP 403 Forbidden` *but* credentials are set                                            | IAM policy too narrow — key can't read the prefix | Apply the IAM policy above                                                |
| `Unable to locate credentials` from `aws s3 cp`                                           | same as above (the workflow's `aws` CLI step)    | Set both Secrets                                                          |
| `Bucket location is not <region>`                                                         | `AWS_REGION` Variable doesn't match the bucket's actual region | Set `vars.AWS_REGION` to the bucket's region                              |

## State convention

`dbt-build.yml` stores the production DuckDB file at `s3://${S3_BUCKET}/state/prod.duckdb`. The first run builds from scratch when the key is absent.

## Conventions enforced in every workflow

Per [`docs/orchestration.md`](../docs/orchestration.md#operational-conventions):

- Pinned action versions (`@v4`, never `@main`)
- `timeout-minutes` set on every job
- `concurrency.group` to prevent overlapping runs racing on shared state
- `workflow_dispatch` on every workflow for manual backfill / debugging
- Slack notification on every run (when `SLACK_WEBHOOK_URL` is set)
