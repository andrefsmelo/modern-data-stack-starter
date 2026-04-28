# Mart exports — producer + consumer

Two concerns live in this directory:

1. **Producer** — `export_marts.py`: writes each dbt mart from `prod.duckdb` to `s3://${S3_BUCKET}/marts/<table>/<table>.parquet`. Runs automatically as the post-`dbt build` step in [`.github/workflows/dbt-build.yml`](../../.github/workflows/dbt-build.yml).
2. **Consumer** — `glue_ddl/*.sql`: external-table DDL that registers those Parquet files in AWS Glue Data Catalog so non-DuckDB engines (Athena, Snowflake, BigQuery, Trino, Spark) can query them.

```
prod.duckdb (in CI)
       │
       ▼
export_marts.py        (producer — automated, runs on every dbt-build)
       │
       ▼
s3://${S3_BUCKET}/marts/<table>/<table>.parquet     (the open artifact)
       │
       ▼
glue_ddl/*.sql         (consumer — one-time per AWS account/region, manual)
       │
       ▼
Athena / Snowflake / BigQuery / Trino / Spark / DuckDB
```

---

## Producer: `export_marts.py`

Runs automatically — nothing to configure beyond what `dbt-build.yml` already needs (`S3_BUCKET`, `AWS_REGION`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`).

To run it locally against your own `prod.duckdb`:

```bash
set -a; source .env; set +a; unset AWS_PROFILE
python transformation/exports/export_marts.py
```

The script writes directly to S3 via DuckDB's `httpfs` extension — no intermediate local Parquet file is produced.

If you add a new mart, add its name to the `MARTS` list at the top of the script.

---

## Consumer: registering the marts in AWS Glue (one-time per AWS account + region)

After the first successful `dbt-build` run has populated `s3://${S3_BUCKET}/marts/`, do this **once** to make the marts queryable from Athena and any other Glue-aware engine.

### Prerequisites

- The Athena Query Editor is set up with a query result location (one-time per region: Athena → Settings → set to `s3://${S3_BUCKET}/athena-results/`).
- Your IAM user/role has `AmazonAthenaFullAccess` and `AWSGlueConsoleFullAccess`, plus `s3:GetObject` + `s3:ListBucket` on `s3://${S3_BUCKET}/marts/*` (the `dbt-build` IAM policy in [`orchestration/README.md`](../../orchestration/README.md#iam-policy-the-aws-key-needs) already covers the S3 part).
- The Athena region matches the bucket region.

### Step 1 — Create the database

In the Athena Query Editor, run:

```sql
CREATE DATABASE IF NOT EXISTS modern_data_stack_marts;
```

Refresh the **Database** dropdown in the left sidebar and select `modern_data_stack_marts`.

### Step 2 — Create one external table per mart

Athena's basic Query Editor only accepts **one statement per Run**. Open each `glue_ddl/*.sql` file in turn, replace `__BUCKET__` with your bucket name, paste it, click Run, repeat for the next file.

Or apply all five at once from the command line:

```bash
BUCKET=modern-data-stack-starter   # your S3_BUCKET value
for f in transformation/exports/glue_ddl/*.sql; do
  echo "==> $f"
  sed "s|__BUCKET__|$BUCKET|g" "$f" \
    | aws athena start-query-execution \
        --query-string file:///dev/stdin \
        --query-execution-context Database=modern_data_stack_marts \
        --result-configuration OutputLocation=s3://$BUCKET/athena-results/
done
```

(Requires `AmazonAthenaFullAccess`. The CLI form is faster for re-bootstrapping in a new account; the UI form is fine for a one-time setup.)

### Step 3 — Verify

```sql
SELECT COUNT(*) FROM modern_data_stack_marts.dim_customers;
-- ~67 rows in the synthetic dataset

SELECT company_name, lifetime_arr, total_facility_limit
FROM modern_data_stack_marts.dim_customers
ORDER BY total_facility_limit DESC NULLS LAST
LIMIT 5;
```

If those return rows, the marts are now visible to **any engine that reads Glue Data Catalog**:

| Engine | How to point it at the catalog |
|---|---|
| **Athena** | works directly after step 2 |
| **Snowflake** | [external table over S3 + Glue catalog integration](https://docs.snowflake.com/en/user-guide/tables-external-intro) |
| **BigQuery** | [BigLake table with AWS connection](https://cloud.google.com/bigquery/docs/biglake-intro) referencing the Glue database |
| **Trino / Spark** | Hive connector pointed at AWS Glue |
| **DuckDB** | `read_parquet('s3://${S3_BUCKET}/marts/<table>/<table>.parquet')` — Glue not required |

---

## Maintenance

Athena re-reads the Parquet files on every query, so when `dbt-build` re-exports the marts on the next cron, queries automatically see the new data — no `MSCK REPAIR`, no Glue Crawler, no metadata refresh.

The schema is fixed in the DDL though. **If you add a column to a mart in dbt:**

1. Update the matching `glue_ddl/<table>.sql` file (column list).
2. Run `ALTER TABLE modern_data_stack_marts.<table> ADD COLUMNS (<col> <type>);` in Athena once.
3. Or `DROP TABLE` + re-run the updated `CREATE EXTERNAL TABLE` statement (faster if multiple columns changed).

---

## Common errors

| Error in Athena | Cause | Fix |
|---|---|---|
| `Only one sql statement is allowed` | Pasted multiple `CREATE EXTERNAL TABLE` blocks at once | Run one statement at a time, or use the CLI loop above |
| `HIVE_METASTORE_ERROR: Database modern_data_stack_marts not found` | Skipped Step 1, or wrong region | Re-run `CREATE DATABASE`, check region selector |
| `HIVE_BAD_DATA: Field <col> incompatible with parquet type` | Column type in DDL ≠ actual Parquet schema | `duckdb -c "DESCRIBE SELECT * FROM read_parquet('s3://${S3_BUCKET}/marts/<table>/<table>.parquet')"`, fix the DDL |
| `Permission denied on S3` | IAM role can read Glue but not the marts S3 prefix | Add `s3:GetObject` + `s3:ListBucket` for `s3://${S3_BUCKET}/marts/*` |
| Table created but `SELECT *` returns 0 rows | Wrong `LOCATION` — typo, missing trailing slash, wrong bucket | `DROP TABLE`, fix `LOCATION`, re-run |
