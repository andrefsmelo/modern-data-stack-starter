-- Staging model: lending.repayments
-- Reads raw_events from S3, extracts JSON data, cleans and type-casts.

{% set source_name = 'lending' %}
{% set entity_name = 'repayments' %}

WITH raw AS (

    {{ read_raw_events(source_name, entity_name) }}

),

extracted AS (

    SELECT
        {{ parse_json_field('data', 'repayment_id') }}       AS repayment_id_raw,
        {{ parse_json_field('data', 'drawdown_id') }}        AS drawdown_id_raw,
        {{ parse_json_field('data', 'facility_id') }}         AS facility_id_raw,
        {{ parse_json_field('data', 'customer_id') }}         AS customer_id_raw,
        {{ parse_json_number('data', 'scheduled_amount') }}   AS scheduled_amount_raw,
        {{ parse_json_number('data', 'actual_amount') }}      AS actual_amount_raw,
        {{ parse_json_field('data', 'currency') }}             AS currency_raw,
        {{ parse_json_field('data', 'due_date') }}             AS due_date_raw,
        {{ parse_json_field('data', 'actual_date') }}          AS actual_date_raw,
        {{ parse_json_field('data', 'status') }}               AS status_raw,
        _ingested_at,
        _schema_version,
        _batch_id

    FROM raw
    WHERE _source = '{{ source_name }}'
      AND _entity = '{{ entity_name }}'

),

cleaned AS (

    SELECT
        repayment_id_raw                                    AS repayment_id,
        drawdown_id_raw                                     AS drawdown_id,
        facility_id_raw                                      AS facility_id,
        customer_id_raw                                      AS customer_id,
        {{ clean_amount('scheduled_amount_raw', 'DECIMAL') }} AS scheduled_amount,
        {{ clean_amount('actual_amount_raw', 'DECIMAL') }}   AS actual_amount,
        {{ clean_currency('currency_raw') }}                  AS currency,
        {{ parse_date('due_date_raw') }}                      AS due_date,
        {{ parse_date('actual_date_raw') }}                   AS actual_date,
        LOWER(status_raw)                                    AS status,
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
                   PARTITION BY repayment_id
                   ORDER BY _ingested_at DESC, _schema_version DESC
               ) AS _row_number
        FROM cleaned
        WHERE repayment_id IS NOT NULL
    )
    WHERE _row_number = 1

)

SELECT
    repayment_id,
    drawdown_id,
    facility_id,
    customer_id,
    scheduled_amount,
    actual_amount,
    currency,
    due_date,
    actual_date,
    status,
    _ingested_at,
    _schema_version
FROM deduplicated