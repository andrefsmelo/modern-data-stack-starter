-- Staging model: lending.drawdowns
-- Reads raw_events from S3, extracts JSON data, cleans and type-casts.

{% set source_name = 'lending' %}
{% set entity_name = 'drawdowns' %}

WITH raw AS (

    {{ read_raw_events(source_name, entity_name) }}

),

extracted AS (

    SELECT
        {{ parse_json_field('data', 'drawdown_id') }}    AS drawdown_id_raw,
        {{ parse_json_field('data', 'facility_id') }}    AS facility_id_raw,
        {{ parse_json_field('data', 'customer_id') }}    AS customer_id_raw,
        {{ parse_json_number('data', 'amount') }}        AS amount_raw,
        {{ parse_json_field('data', 'currency') }}       AS currency_raw,
        {{ parse_json_field('data', 'drawdown_date') }}  AS drawdown_date_raw,
        {{ parse_json_field('data', 'purpose') }}         AS purpose,
        {{ parse_json_field('data', 'status') }}          AS status_raw,
        _ingested_at,
        _schema_version,
        _batch_id

    FROM raw
    WHERE _source = '{{ source_name }}'
      AND _entity = '{{ entity_name }}'

),

cleaned AS (

    SELECT
        drawdown_id_raw                                    AS drawdown_id,
        facility_id_raw                                     AS facility_id,
        customer_id_raw                                     AS customer_id,
        CASE
            WHEN {{ clean_amount('amount_raw', 'DECIMAL') }} < 0 THEN NULL
            ELSE {{ clean_amount('amount_raw', 'DECIMAL') }}
        END                                                AS amount,
        {{ clean_currency('currency_raw') }}               AS currency,
        {{ parse_date('drawdown_date_raw') }}              AS drawdown_date,
        purpose,
        LOWER(status_raw)                                  AS status,
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
                   PARTITION BY drawdown_id
                   ORDER BY _ingested_at DESC, _schema_version DESC
               ) AS _row_number
        FROM cleaned
    )
    WHERE _row_number = 1

)

SELECT
    drawdown_id,
    facility_id,
    customer_id,
    amount,
    currency,
    drawdown_date,
    purpose,
    status,
    _ingested_at,
    _schema_version
FROM deduplicated