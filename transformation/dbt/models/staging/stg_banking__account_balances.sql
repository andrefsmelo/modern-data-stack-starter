-- Staging model: banking.account_balances
-- Reads raw_events from S3, extracts JSON data, cleans and type-casts.

{% set source_name = 'banking' %}
{% set entity_name = 'account_balances' %}

WITH raw AS (

    {{ read_raw_events(source_name, entity_name) }}

),

extracted AS (

    SELECT
        {{ parse_json_field('data', 'snapshot_id') }}      AS snapshot_id_raw,
        {{ parse_json_field('data', 'customer_id') }}      AS customer_id_raw,
        {{ parse_json_field('data', 'account_id') }}         AS account_id,
        {{ parse_json_field('data', 'currency') }}           AS currency_raw,
        {{ parse_json_number('data', 'balance') }}          AS balance_raw,
        {{ parse_json_field('data', 'snapshot_date') }}      AS snapshot_date_raw,
        {{ parse_json_field('data', 'account_type') }}       AS account_type_raw,
        _ingested_at,
        _schema_version,
        _batch_id

    FROM raw
    WHERE _source = '{{ source_name }}'
      AND _entity = '{{ entity_name }}'

),

cleaned AS (

    SELECT
        snapshot_id_raw                                     AS snapshot_id,
        customer_id_raw                                     AS customer_id,
        account_id,
        {{ clean_currency('currency_raw') }}                AS currency,
        CASE
            WHEN {{ clean_amount('balance_raw', 'DECIMAL') }} < 0 THEN NULL
            ELSE {{ clean_amount('balance_raw', 'DECIMAL') }}
        END                                                AS balance,
        {{ parse_date('snapshot_date_raw') }}               AS snapshot_date,
        LOWER(account_type_raw)                             AS account_type,
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
                   PARTITION BY snapshot_id
                   ORDER BY _ingested_at DESC, _schema_version DESC
               ) AS _row_number
        FROM cleaned
        WHERE snapshot_id IS NOT NULL
    )
    WHERE _row_number = 1

)

SELECT
    snapshot_id,
    customer_id,
    account_id,
    currency,
    balance,
    snapshot_date,
    account_type,
    _ingested_at,
    _schema_version
FROM deduplicated