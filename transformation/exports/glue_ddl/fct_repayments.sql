-- Athena / AWS Glue Data Catalog DDL for the fct_repayments mart.
-- Replace __BUCKET__ with the value of S3_BUCKET before running.

CREATE EXTERNAL TABLE IF NOT EXISTS modern_data_stack_marts.fct_repayments (
  repayment_id                  string,
  drawdown_id                   string,
  facility_id                   string,
  customer_id                   string,
  scheduled_amount              decimal(18,2),
  actual_amount                 decimal(18,2),
  currency                      string,
  due_date                      timestamp,
  actual_date                   timestamp,
  scheduled_vs_actual_lag_days  bigint,
  status                        string,
  is_orphaned                   boolean
)
STORED AS PARQUET
LOCATION 's3://__BUCKET__/marts/fct_repayments/';
