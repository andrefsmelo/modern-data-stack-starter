-- Athena / AWS Glue Data Catalog DDL for the fct_fx_transactions mart.
-- Replace __BUCKET__ with the value of S3_BUCKET before running.

CREATE EXTERNAL TABLE IF NOT EXISTS modern_data_stack_marts.fct_fx_transactions (
  transaction_id    string,
  customer_id       string,
  base_currency     string,
  quote_currency    string,
  currency_pair     string,
  notional_base     decimal(18,2),
  notional_quote    decimal(18,2),
  effective_rate    double,
  rate_type         string,
  transaction_date  timestamp,
  is_orphaned       boolean
)
STORED AS PARQUET
LOCATION 's3://__BUCKET__/marts/fct_fx_transactions/';
