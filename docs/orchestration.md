# Orchestration

> How to run scheduled and event-driven jobs on ephemeral compute — "build a machine, run the job, turn it off" — without operating a 24/7 orchestrator. Calibrated for a company up to ~50 employees.

The day-to-day rule lives in [architecture.md](architecture.md) (orchestration row of the Phase 1 table). This document is the deep-dive: when GitHub Actions is enough, when to escape to Lambda / Fargate / Modal / Cloud Run, what to specifically *not* do, and the actual pricing math.

-----

## The pattern

For batch ingestion and dbt jobs, the right shape is **ephemeral compute**:

```
[Trigger]              cron schedule, S3 event, manual button
   │
   ▼
[Provision a machine]  10-second cold start, fresh OS, configured by code
   │
   ▼
[Run the job]          dlt sync / dbt build / OCR extraction
   │
   ▼
[Tear it down]         no idle bill, logs persisted to the trigger system
```

You should be paying **zero dollars** when no job is running. Anything that keeps a VM alive between runs (Airflow on EC2, a self-hosted scheduler) violates the pattern at this scale.

-----

## Default: GitHub Actions

A `ubuntu-latest` runner *is* the ephemeral machine. The runner provisions in ~10 seconds, runs your steps, and is destroyed. Schedules use cron syntax. Secrets, logs, and notifications are first-class.

```yaml
# .github/workflows/ingest-stripe.yml
on:
  schedule:
    - cron: '0 */6 * * *'   # every 6 hours
  workflow_dispatch:        # manual trigger button
jobs:
  ingest:
    runs-on: ubuntu-latest   # 4 vCPU, 16 GB RAM, free
    timeout-minutes: 60
    concurrency:
      group: ingest-stripe   # prevents overlapping runs
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: '3.11' }
      - run: pip install -r requirements.txt
      - run: python ingestion/dlt_pipelines/stripe.py
        env:
          AWS_ACCESS_KEY_ID: ${{ secrets.AWS_ACCESS_KEY_ID }}
          AWS_SECRET_ACCESS_KEY: ${{ secrets.AWS_SECRET_ACCESS_KEY }}
          S3_BUCKET: ${{ vars.S3_BUCKET }}
```

That's the entire orchestrator. No new infrastructure. No new vendor.

### Standard runner specs

| Resource | `ubuntu-latest` (free tier) |
|---|---|
| vCPU | 4 |
| RAM | 16 GB |
| Disk | 14 GB free |
| Max job duration | 6 hours |
| Cold start | ~10 seconds |
| Network egress | unmetered (S3 transfer is paid by AWS) |

-----

## Pricing — what you actually pay

### Compute (Linux runners)

| Repo type | Free quota | Beyond free |
|---|---|---|
| **Public repo** | unlimited | N/A |
| **Private repo (Free plan)** | 2,000 min/month | $0.008/min ≈ $0.48/hour |
| **Private repo (Team plan, $4/user/mo)** | 3,000 min/month | $0.008/min |
| **Private repo (Enterprise)** | 50,000 min/month | $0.008/min |

Notes:
- Windows costs **2×** per minute, macOS **10×**. Always pick `ubuntu-latest`.
- **Larger runners** (8/16/32/64 vCPU) and **GPU runners** are *not* in the free tier — billed from the first minute.
- Storage and bandwidth (artifacts, package registry) are billed separately from compute minutes.
- **Egress to S3** is paid by AWS (S3 ingress is free; only egress costs), not by GitHub.

### Realistic Phase 1 usage

| Job | Duration | Frequency | Minutes/month |
|---|---|---|---|
| dlt sync (3 sources × 2 min) | 6 min | every 6 hours | 720 |
| dbt build (full project) | 5 min | every 6 hours | 600 |
| Daily backfill / heavy job | 15 min | daily | 450 |
| **Total** | | | **~1,770** |

Fits inside the 2,000-minute free tier. **You pay $0.**

### When you actually start paying

- Private repo *and* you exceed 2,000 min/month → ~$0.48/hour beyond.
- Larger runner (e.g. 16 vCPU, 64 GB) → paid from minute one.
- GPU runner → paid from minute one, and noticeably more expensive.

If you blow past the free tier and run, say, 5,000 min/month on standard Linux:

```
(5,000 − 2,000) × $0.008 = $24/month
```

Still cheaper than a dedicated VM, and you only pay during execution.

-----

## When GitHub Actions doesn't fit

The free-tier runner has four real limits. If none of these bite, **don't migrate**.

| Limit | Workaround inside GH Actions | When to escape |
|---|---|---|
| 6-hour max job | Split into smaller jobs; chain via `needs:` | Genuinely > 6h after splitting |
| 16 GB RAM | Use `larger-runner` (paid) — up to 64 GB | Need > 64 GB or sustained high RAM is too expensive |
| No GPU on free tier | Use `ubuntu-latest-gpu` (paid) | Heavy GPU usage where Actions GPU is too expensive |
| ~10-second cold start | Use `concurrency` to keep recent runs warm | Need < 1-second response to an S3 event |

### Escape hatches, in order of preference

#### AWS Lambda — for short, event-driven jobs
- **Use when**: the trigger is "a file landed in S3" or "an API webhook fired", AND the job runs in < 15 minutes.
- **Limits**: 15-minute hard timeout, 10 GB RAM max, 250 MB unzipped package (or 10 GB container image).
- **Pricing**: pay per ms; first 1M requests/month free.
- **Best fit in this stack**: per-document OCR triggered by S3 upload (Scenario D in the README). The doc lands → Lambda fires → extracted Parquet written back → done.

#### AWS Fargate scheduled tasks — for jobs > 6 hours or > 16 GB
- **Use when**: a job is too long or too big for GH Actions but you don't want to operate EC2.
- **Setup**: container image in ECR, ECS task definition, EventBridge rule for the cron.
- **Pricing**: pay per second of vCPU + RAM during execution. No idle bill.
- **Best fit**: the rare large backfill job, or memory-heavy ingestion of a big source.

#### Modal — Python-native ephemeral compute
- **Use when**: you want GH Actions ergonomics with GPU support and a higher RAM ceiling, without learning ECS.
- **How it looks**:
  ```python
  @app.function(schedule=modal.Cron("0 */6 * * *"), gpu="A10G")
  def run_ocr_batch():
      ...
  ```
- **Pricing**: per-second, generous free tier ($30/month credit at time of writing).
- **Best fit**: self-hosted PaddleOCR / docTR jobs that need a GPU.

#### Google Cloud Run jobs — managed container, run-to-completion
- **Use when**: you're on GCP and want the same shape as Fargate.
- **Setup**: container image in Artifact Registry, Cloud Run job, Cloud Scheduler for cron.
- **Pricing**: per-second, free tier covers small workloads.
- **Best fit**: GCP-native version of the Fargate scheduled-task pattern.

#### AWS Batch — for many parallel jobs or GPU pools
- **Use when**: 1000s of jobs/hour, or fleet GPU work.
- **Best fit**: not Phase 1. If you reach this scale, you've outgrown this whole document.

-----

## Decision rule

| Your situation | Use |
|---|---|
| Scheduled batch ingestion or dbt build | **GitHub Actions** |
| S3-event-triggered, < 15 min (e.g. OCR-on-upload) | **AWS Lambda** |
| Scheduled job > 6 hours OR needs > 16 GB RAM | **AWS Fargate scheduled task** (or **Cloud Run jobs** on GCP) |
| Needs GPU and you're a Python team | **Modal** |
| Many parallel jobs (1000s/hour) | **AWS Batch** — but you've outgrown Phase 1 |
| Large pipeline graph with cross-job dependencies | **Prefect Cloud** or **Dagster Cloud** — see [evolution-triggers.md](evolution-triggers.md#orchestration) |

-----

## Anti-patterns

- **Airflow on a 24/7 VM** for < 10 pipelines. You're now operating an orchestrator full-time to schedule jobs that GH Actions cron does for free.
- **Kubernetes CronJobs** when you don't already operate a Kubernetes cluster for other reasons. The cluster bill alone exceeds the entire Phase 1 budget.
- **EC2 + crontab + a custom "spin up / tear down" Bash script.** That code already exists, it's called GitHub Actions and Fargate. Don't reinvent it.
- **A persistent Airbyte VM "because we'll need orchestration eventually."** If your only ingestion is Airbyte, Airbyte's built-in scheduler is enough. Add Prefect / Dagster only when triggers from [evolution-triggers.md#orchestration](evolution-triggers.md#orchestration) actually fire.
- **Triggering Lambda from a cron schedule for jobs that take more than a few minutes.** That's what GH Actions is for. Lambda's strength is event-driven, not time-driven.
- **Keeping secrets in plain `.env` files committed to the repo to "make GH Actions easier".** Always use GitHub Actions Secrets — see [architecture.md → Secrets](architecture.md#secrets).

-----

## Operational conventions

- **One workflow file per pipeline**, named after the pipeline (`ingest-stripe.yml`, `dbt-build.yml`). Easier to disable/debug a single job.
- **Always set `timeout-minutes`**. A stuck job in CI is a stuck job that bills you for the full 6-hour ceiling.
- **Always set `concurrency.group`** for jobs that mutate shared state (e.g. `prod.duckdb`). Prevents overlapping runs racing on the same artifact.
- **Always emit a Slack notification on failure**. A job failing silently is worse than no job at all. See [architecture.md → Observability](architecture.md#observability).
- **Pin action versions** (`actions/checkout@v4`, not `@main`). Floating refs break unpredictably.
- **Use `workflow_dispatch`** on every workflow so you have a manual run button — invaluable for backfills and debugging.

-----

## References

- [GitHub Actions billing](https://docs.github.com/en/billing/concepts/product-billing/github-actions)
- [GitHub Actions larger runners](https://docs.github.com/en/actions/using-github-hosted-runners/about-larger-runners)
- [AWS Lambda limits](https://docs.aws.amazon.com/lambda/latest/dg/gettingstarted-limits.html)
- [AWS Fargate scheduled tasks](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/scheduled_tasks.html)
- [Modal](https://modal.com/docs)
- [Google Cloud Run jobs](https://cloud.google.com/run/docs/create-jobs)
