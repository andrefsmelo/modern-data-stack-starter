-- Staging model: banking.fx_transactions
-- Reads raw_events from S3, extracts JSON data, cleans and type-casts.

{% set source_name = 'banking' %}
{% set entity_name = 'fx_transactions' %}

WITH raw AS (

    {{ read_raw_events(source_name, entity_name) }}

),

extracted AS (

    SELECT
        {{ parse_json_field('data', 'transaction_id') }}    AS transaction_id_raw,
        {{ parse_json_field('data', 'customer_id') }}      AS customer_id_raw,
        {{ parse_json_field('data', 'base_currency') }}     AS base_currency_raw,
        {{ parse_json_field('data', 'quote_currency') }}    AS quote_currency_raw,
        {{ parse_json_number('data', 'base_amount') }}     AS base_amount_raw,
        {{ parse_json_number('data', 'quote_amount') }}    AS quote_amount_raw,
        {{ parse_json_number('data', 'rate') }}             AS rate_raw,
        {{ parse_json_field('data', 'rate_type') }}         AS rate_type,
        {{ parse_json_field('data', 'transaction_date') }}  AS transaction_date_raw,
        COALESCE({{ parse_json_field('data', 'counterparty_bank_bic') }}, NULL) AS counterparty_bank_bic,
        _ingested_at,
        _schema_version,
        _batch_id

    FROM raw
    WHERE _source = '{{ source_name }}'
      AND _entity = '{{ entity_name }}'

),

cleaned AS (

    SELECT
        transaction_id_raw                                 AS transaction_id,
        customer_id_raw                                     AS customer_id,
        {{ clean_currency('base_currency_raw') }}           AS base_currency,
        {{ clean_currency('quote_currency_raw') }}          AS quote_currency,
        {{ clean_amount('base_amount_raw', 'DECIMAL') }}   AS base_amount,
        {{ clean_amount('quote_amount_raw', 'DECIMAL') }}  AS quote_amount,
        TRY_CAST(rate_raw AS DOUBLE)                        AS rate,
        rate_type,
        {{ parse_date('transaction_date_raw') }}            AS transaction_date,
        COALESCE(counterparty_bank_bic, NULL)               AS counterparty_bank_bic,
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
                   PARTITION BY transaction_id
                   ORDER BY _ingested_at DESC, _schema_version DESC
               ) AS _row_number
        FROM cleaned
        WHERE transaction_id IS NOT NULL
    )
    WHERE _row_number = 1

)

SELECT
    transaction_id,
    customer_id,
    base_currency,
    quote_currency,
    base_amount,
    quote_amount,
    rate,
    rate_type,
    transaction_date,
    counterparty_bank_bic,
    _ingested_at,
    _schema_version
FROM deduplicated