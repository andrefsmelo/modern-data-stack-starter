-- Athena / AWS Glue Data Catalog DDL for the dim_credit_facilities mart.
-- Replace __BUCKET__ with the value of S3_BUCKET before running.

CREATE EXTERNAL TABLE IF NOT EXISTS modern_data_stack_marts.dim_credit_facilities (
  facility_id              string,
  application_id           string,
  customer_id              string,
  facility_limit           decimal(18,2),
  currency                 string,
  approval_date            timestamp,
  maturity_date            timestamp,
  facility_status          string,
  interest_rate            double,
  current_utilization_pct  double,
  is_orphaned              boolean
)
STORED AS PARQUET
LOCATION 's3://__BUCKET__/marts/dim_credit_facilities/';
