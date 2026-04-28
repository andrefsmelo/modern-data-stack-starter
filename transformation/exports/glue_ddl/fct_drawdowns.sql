-- Athena / AWS Glue Data Catalog DDL for the fct_drawdowns mart.
-- Replace __BUCKET__ with the value of S3_BUCKET before running.

CREATE EXTERNAL TABLE IF NOT EXISTS modern_data_stack_marts.fct_drawdowns (
  drawdown_id                   string,
  facility_id                   string,
  customer_id                   string,
  amount                        decimal(18,2),
  currency                      string,
  drawdown_date                 timestamp,
  purpose                       string,
  status                        string,
  days_since_facility_approval  bigint,
  is_orphaned                   boolean
)
STORED AS PARQUET
LOCATION 's3://__BUCKET__/marts/fct_drawdowns/';
