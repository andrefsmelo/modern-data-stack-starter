-- Staging model: lending.loan_applications
-- Reads raw_events from S3, extracts JSON data, cleans and type-casts.

{% set source_name = 'lending' %}
{% set entity_name = 'loan_applications' %}

WITH raw AS (

    {{ read_raw_events(source_name, entity_name) }}

),

extracted AS (

    SELECT
        {{ parse_json_field('data', 'application_id') }}            AS application_id_raw,
        {{ parse_json_field('data', 'customer_id') }}                AS customer_id_raw,
        {{ parse_json_field('data', 'company_name') }}              AS company_name,
        {{ parse_json_field('data', 'company_registration_number') }} AS company_registration_number_raw,
        {{ parse_json_field('data', 'country_code') }}              AS country_code_raw,
        {{ parse_json_field('data', 'industry') }}                   AS industry,
        {{ parse_json_number('data', 'requested_amount') }}         AS requested_amount_raw,
        {{ parse_json_field('data', 'currency') }}                  AS currency_raw,
        {{ parse_json_field('data', 'application_date') }}          AS application_date_raw,
        {{ parse_json_field('data', 'status') }}                    AS status_raw,
        {{ parse_json_number('data', 'credit_score') }}             AS credit_score_raw,
        {{ parse_json_field('data', 'risk_rating') }}               AS risk_rating,
        {{ parse_json_number('data', 'headcount_at_application') }} AS headcount_at_application_raw,
        {{ parse_json_number('data', 'valuation_at_application') }} AS valuation_at_application_raw,
        {{ parse_json_number('data', 'arr_at_application') }}       AS arr_at_application_raw,
        COALESCE({{ parse_json_field('data', 'referral_source') }}, NULL) AS referral_source,
        _ingested_at,
        _schema_version,
        _batch_id

    FROM raw
    WHERE _source = '{{ source_name }}'
      AND _entity = '{{ entity_name }}'

),

cleaned AS (

    SELECT
        application_id_raw                                          AS application_id,
        customer_id_raw                                             AS customer_id,
        company_name,
        NULLIF(company_registration_number_raw, '')                AS company_registration_number,
        CASE
            WHEN UPPER(country_code_raw) IN (
                'GB', 'US', 'CA', 'CH', 'SE', 'NO', 'DK', 'IS',
                'DE', 'FR', 'IT', 'ES', 'NL', 'BE', 'AT', 'PT',
                'IE', 'FI', 'LU', 'EE', 'LV', 'LT', 'SI', 'SK',
                'MT', 'CY', 'GR', 'HR', 'PL', 'CZ', 'HU', 'RO',
                'BG', 'LI'
            ) THEN UPPER(country_code_raw)
            ELSE NULL
        END                                                        AS country_code,
        industry,
        {{ clean_amount('requested_amount_raw', 'DECIMAL') }}      AS requested_amount,
        {{ clean_currency('currency_raw') }}                        AS currency,
        {{ parse_date('application_date_raw') }}                    AS application_date,
        LOWER(status_raw)                                           AS status,
        CASE
            WHEN TRY_CAST(credit_score_raw AS BIGINT) BETWEEN 300 AND 850
                THEN TRY_CAST(credit_score_raw AS BIGINT)
            ELSE NULL
        END                                                        AS credit_score,
        risk_rating,
        COALESCE(TRY_CAST(headcount_at_application_raw AS BIGINT), 0) AS headcount_at_application,
        {{ clean_amount('valuation_at_application_raw', 'DECIMAL') }} AS valuation_at_application,
        {{ clean_amount('arr_at_application_raw', 'DECIMAL') }}      AS arr_at_application,
        COALESCE(referral_source, NULL)                              AS referral_source,
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
                   PARTITION BY application_id
                   ORDER BY _ingested_at DESC, _schema_version DESC
               ) AS _row_number
        FROM cleaned
        WHERE application_id IS NOT NULL
    )
    WHERE _row_number = 1

)

SELECT
    application_id,
    customer_id,
    company_name,
    company_registration_number,
    country_code,
    industry,
    requested_amount,
    currency,
    application_date,
    status,
    credit_score,
    risk_rating,
    headcount_at_application,
    valuation_at_application,
    arr_at_application,
    referral_source,
    _ingested_at,
    _schema_version
FROM deduplicated