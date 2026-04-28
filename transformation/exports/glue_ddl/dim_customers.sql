-- Athena / AWS Glue Data Catalog DDL for the dim_customers mart.
-- Replace __BUCKET__ with the value of S3_BUCKET before running:
--   sed 's|__BUCKET__|modern-data-stack-starter|g' dim_customers.sql

CREATE EXTERNAL TABLE IF NOT EXISTS modern_data_stack_marts.dim_customers (
  customer_id                  string,
  company_name                 string,
  country_code                 string,
  industry                     string,
  headcount_at_application     bigint,
  valuation_at_application     decimal(18,2),
  arr_at_application           decimal(18,2),
  lifetime_arr                 double,
  arr_growth_pct               double,
  total_facility_limit         decimal(38,2),
  total_drawn_amount           decimal(38,2),
  primary_account_currency     string,
  current_headcount            bigint,
  current_valuation            decimal(18,2),
  team_growth_pct              double,
  valuation_increase_multiple  double,
  arr_variance_pct             double,
  is_orphaned                  boolean
)
STORED AS PARQUET
LOCATION 's3://__BUCKET__/marts/dim_customers/';
