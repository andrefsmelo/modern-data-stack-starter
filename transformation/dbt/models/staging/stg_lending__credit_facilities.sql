-- Staging model: lending.credit_facilities
-- Reads raw_events from S3, extracts JSON data, cleans and type-casts.

{% set source_name = 'lending' %}
{% set entity_name = 'credit_facilities' %}

WITH raw AS (

    {{ read_raw_events(source_name, entity_name) }}

),

extracted AS (

    SELECT
        {{ parse_json_field('data', 'facility_id') }}          AS facility_id_raw,
        {{ parse_json_field('data', 'customer_id') }}          AS customer_id_raw,
        {{ parse_json_field('data', 'application_id') }}       AS application_id_raw,
        {{ parse_json_number('data', 'facility_limit') }}      AS facility_limit_raw,
        {{ parse_json_field('data', 'currency') }}              AS currency_raw,
        {{ parse_json_field('data', 'approval_date') }}         AS approval_date_raw,
        {{ parse_json_field('data', 'maturity_date') }}         AS maturity_date_raw,
        {{ parse_json_field('data', 'status') }}                AS status_raw,
        {{ parse_json_number('data', 'interest_rate') }}       AS interest_rate_raw,
        {{ parse_json_field('data', 'repayment_schedule_json') }} AS repayment_schedule_json,
        COALESCE({{ parse_json_field('data', 'collateral_required') }}, NULL) AS collateral_required,
        _ingested_at,
        _schema_version,
        _batch_id

    FROM raw
    WHERE _source = '{{ source_name }}'
      AND _entity = '{{ entity_name }}'

),

cleaned AS (

    SELECT
        facility_id_raw                                    AS facility_id,
        customer_id_raw                                    AS customer_id,
        application_id_raw                                 AS application_id,
        CASE
            WHEN {{ clean_amount('facility_limit_raw', 'DECIMAL') }} < 0 THEN NULL
            ELSE {{ clean_amount('facility_limit_raw', 'DECIMAL') }}
        END                                                AS facility_limit,
        {{ clean_currency('currency_raw') }}               AS currency,
        {{ parse_date('approval_date_raw') }}              AS approval_date,
        {{ parse_date('maturity_date_raw') }}               AS maturity_date,
        LOWER(status_raw)                                  AS status,
        TRY_CAST(interest_rate_raw AS DOUBLE)              AS interest_rate,
        repayment_schedule_json,
        COALESCE(collateral_required, NULL)                AS collateral_required,
        _ingested_at,
        _schema_version,
        _batch_id

    FROM extracted

),

deduplicated AS (

    SELECT *
    FROM (
        SELECT *,
               ROW_NUMBER() OVER (
                   PARTITION BY facility_id
                   ORDER BY _ingested_at DESC, _schema_version DESC
               ) AS _row_number
        FROM cleaned
        WHERE facility_id IS NOT NULL
    )
    WHERE _row_number = 1

)

SELECT
    facility_id,
    customer_id,
    application_id,
    facility_limit,
    currency,
    approval_date,
    maturity_date,
    status,
    interest_rate,
    repayment_schedule_json,
    collateral_required,
    _ingested_at,
    _schema_version
FROM deduplicated