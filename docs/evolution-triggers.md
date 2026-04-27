# Evolution Triggers

> A per-layer playbook of operational signals that should drive a change in the data platform — and the recommended next move when each signal fires.

This document complements [architecture.md](architecture.md). The architecture document describes **what the stack looks like** at each phase; this one describes **when and why to move**, layer by layer, including intermediate steps that can defer a full Phase 2 jump.

## How to use this document

- Each section covers one layer (Storage, Compute, Ingestion, Orchestration, Observability).
- Each trigger has three parts: **Signal** (what you measure), **Threshold** (when to act), **Action** (what to do).
- Triggers are independent: hitting one in storage does not force a change in compute. Migrate the smallest unit that solves the pain.
- Re-evaluate quarterly. A trigger that fired but later resolved (e.g. a one-off backfill) is not a reason to migrate.

-----

## Storage

### Trigger S1 — Raw data volume growth

| | |
|---|---|
|**Signal**|Total bytes in `s3://{bucket}/raw/` measured monthly.|
|**Threshold**|Sustained > 200 GB for 2 consecutive months, or > 500 GB at any single point.|
|**Action**|Adopt **Apache Iceberg** on top of the existing S3 layout. Keep the same bucket; add Iceberg metadata. DuckDB, BigQuery, and Snowflake can all read Iceberg tables directly, so no re-ingest is needed.|

### Trigger S2 — Need for ACID writes or schema evolution

| | |
|---|---|
|**Signal**|Recurring data corruption from concurrent writers, or breaking schema changes that require full table rewrites.|
|**Threshold**|More than one incident per quarter.|
|**Action**|Adopt **Iceberg** (preferred) or **Delta Lake**. Iceberg is favored for its multi-engine support and lighter operational footprint.|

### Trigger S3 — Multi-engine reads

| | |
|---|---|
|**Signal**|Two or more query engines (e.g. DuckDB for ad-hoc, BigQuery for dashboards) reading the same raw data.|
|**Threshold**|As soon as a second engine appears.|
|**Action**|Wrap raw data in Iceberg so both engines see consistent snapshots. Avoids dual-loading the same data into a warehouse.|

### Trigger S4 — Egress cost spike

| | |
|---|---|
|**Signal**|Monthly S3 data-transfer bill.|
|**Threshold**|Sustained > $50/month for outbound transfer.|
|**Action**|Audit which consumer is pulling data cross-region. Either co-locate the consumer, or — only if the bill stays high after consolidation — re-evaluate Cloudflare R2 (zero egress, S3-compatible).|

-----

## Compute / Transformation

### Trigger C1 — DuckDB query latency

| | |
|---|---|
|**Signal**|`dbt run` wall-clock time on the slowest mart model.|
|**Threshold**|Consistently > 5 minutes per model after partition pruning and predicate pushdown have been verified.|
|**Action**|First, scale the GitHub Actions runner up to a **larger runner** (e.g. 8 vCPU, 32 GB) — buys 2–3× headroom for ~$0.05/job. Only if that is insufficient, move to **BigQuery on-demand** or **Snowflake X-Small**.|

### Trigger C2 — Total daily compute cost

| | |
|---|---|
|**Signal**|GitHub Actions minutes consumed per day by `dbt` workflows.|
|**Threshold**|> 4 hours/day on the largest runner.|
|**Action**|Move marts to BigQuery / Snowflake. Keep staging models on DuckDB if cost-effective — heterogeneous compute is fine when boundaries are stable Iceberg tables.|

### Trigger C3 — Concurrent query needs

| | |
|---|---|
|**Signal**|Multiple analysts blocked waiting for the single `prod.duckdb` lock during work hours.|
|**Threshold**|Reported > 1× per week by any analyst.|
|**Action**|Move serving-layer models to a managed warehouse (BigQuery / Snowflake). DuckDB is single-writer; managed warehouses are not.|

### Trigger C4 — Need for fine-grained access control

| | |
|---|---|
|**Signal**|Stakeholders ask for row-level or column-level security (e.g. analysts can see all customers except a specific cohort).|
|**Threshold**|First request that cannot be solved with a separate dbt model.|
|**Action**|Move serving layer to BigQuery / Snowflake — both have native row/column policies. DuckDB does not.|

-----

## Ingestion

### Trigger I1 — Source count growth

| | |
|---|---|
|**Signal**|Number of distinct ingestion sources running on a schedule.|
|**Threshold**|> 10 sources, or > 5 sources where any one fails more than weekly.|
|**Action**|Two options, pick based on team preference:<br>**(a) Airbyte Cloud** — managed, $X/month per connector, eliminates the self-hosted VM. Best when the team does not want to operate infra.<br>**(b) Dedicated Airbyte VM** (8 GB RAM, ~$40/month) with proper monitoring, backups, and connector pinning. Best when cost matters more than ops time.|

### Trigger I2 — Self-hosted Airbyte instability

| | |
|---|---|
|**Signal**|Airbyte container OOMs, restarts, or sync failures attributable to the host.|
|**Threshold**|> 1 incident per week for 2 consecutive weeks.|
|**Action**|Immediately move to a 4 GB → 8 GB VM. If instability persists after upsizing, migrate to Airbyte Cloud (Trigger I1, option a).|

### Trigger I3 — High-volume source

| | |
|---|---|
|**Signal**|A single source produces > 10 GB/day.|
|**Threshold**|Sustained for 7 days.|
|**Action**|Move that one source off Airbyte and onto a **dedicated dlt or Spark job** with explicit incremental state. Airbyte's row-by-row architecture is not the right tool for bulk extracts.|

### Trigger I4 — CDC requirement

| | |
|---|---|
|**Signal**|Stakeholders need < 1-hour freshness from an operational database.|
|**Threshold**|First serious request.|
|**Action**|This is an architectural shift, not a trigger to scale within Phase 1. Evaluate **Debezium + Kafka** or a managed CDC vendor (Fivetran HVR, Airbyte CDC connectors). Update the architecture doc's non-goals before adopting.|

-----

## Orchestration

### Trigger O1 — Pipeline count

| | |
|---|---|
|**Signal**|Number of distinct GitHub Actions workflows running data jobs.|
|**Threshold**|> 10 workflows, or > 3 workflows with cross-workflow dependencies expressed as cron offsets ("Run B 30 min after A and hope A finished").|
|**Action**|Adopt **Prefect Cloud** or **Dagster Cloud**. Both have free tiers sufficient for < 50 jobs. Prefect is lighter to onboard; Dagster has stronger asset-based modeling.|

### Trigger O2 — Backfill needs

| | |
|---|---|
|**Signal**|Frequency of "re-run model X for date range Y" requests.|
|**Threshold**|> 2 backfills per month done manually.|
|**Action**|Move to Dagster (asset-based) or implement explicit `dbt --vars` backfill workflows. Dagster's partition model is the cleanest answer here.|

### Trigger O3 — SLA / freshness alerting

| | |
|---|---|
|**Signal**|Stakeholders complain about stale dashboards before the team notices.|
|**Threshold**|Once.|
|**Action**|Add `dbt source freshness` checks (already in conventions) **and** a Prefect/Dagster SLA timer. This is mandatory before promising any external SLA.|

-----

## Observability

### Trigger Ob1 — Failures discovered late

| | |
|---|---|
|**Signal**|Time between a pipeline failure and the team noticing.|
|**Threshold**|> 2 hours, more than once.|
|**Action**|Confirm Slack notifications fire on every workflow failure. Add a daily "no news is good news" digest workflow that posts a green check if all jobs ran.|

### Trigger Ob2 — Cross-system correlation

| | |
|---|---|
|**Signal**|Incident postmortems require pulling logs from > 2 systems (GitHub Actions + Airbyte + S3).|
|**Threshold**|> 1 such incident per month.|
|**Action**|Adopt **Sentry** (errors) and **Grafana Cloud** (metrics, free tier). Forward dbt artifacts and Airbyte logs to a single store. Pre-Phase-3, avoid Datadog — pricing escalates fast.|

### Trigger Ob3 — Data quality regressions

| | |
|---|---|
|**Signal**|`severity: warn` dbt test failures noticed by stakeholders before the team triages them.|
|**Threshold**|Once.|
|**Action**|Adopt **Elementary** (open source) on top of dbt. It surfaces test failures and freshness issues without requiring a paid platform.|

-----

## Anti-Triggers (do **not** migrate when…)

- A single incident: one slow query, one OOM, one missed SLA. Wait for a second occurrence before acting.
- A vendor's marketing email tells you to.
- An engineer is bored and wants to try a new tool.
- You "might" need it in 12 months. Revisit in 12 months.

-----

## Review cadence

Open this document at the start of each quarter. For each trigger:

1. Pull the relevant metric (S3 volume, GH Actions minutes, source count, etc.).
2. Mark green / yellow / red against the threshold.
3. For any red, open a planning ticket; do not migrate impulsively.
4. Update thresholds if your context has changed (e.g. team size, product stage).
