-- Staging model: payments.invoices
-- Reads raw_events from S3, extracts JSON data, cleans and type-casts.

{% set source_name = 'payments' %}
{% set entity_name = 'invoices' %}

WITH raw AS (

    {{ read_raw_events(source_name, entity_name) }}

),

extracted AS (

    SELECT
        {{ parse_json_field('data', 'invoice_id') }}          AS invoice_id_raw,
        {{ parse_json_field('data', 'customer_id') }}         AS customer_id_raw,
        {{ parse_json_field('data', 'subscription_id') }}     AS subscription_id_raw,
        {{ parse_json_number('data', 'amount') }}              AS amount_raw,
        {{ parse_json_field('data', 'currency') }}            AS currency_raw,
        {{ parse_json_field('data', 'invoice_date') }}        AS invoice_date_raw,
        {{ parse_json_field('data', 'due_date') }}            AS due_date_raw,
        {{ parse_json_field('data', 'paid_at') }}             AS paid_at_raw,
        {{ parse_json_field('data', 'status') }}               AS status_raw,
        {{ parse_json_field('data', 'line_items_json') }}     AS line_items_json,
        _ingested_at,
        _schema_version,
        _batch_id

    FROM raw
    WHERE _source = '{{ source_name }}'
      AND _entity = '{{ entity_name }}'

),

cleaned AS (

    SELECT
        invoice_id_raw                                    AS invoice_id,
        customer_id_raw                                   AS customer_id,
        subscription_id_raw                                AS subscription_id,
        {{ clean_amount('amount_raw', 'DECIMAL') }}        AS amount,
        {{ clean_currency('currency_raw') }}              AS currency,
        {{ parse_date('invoice_date_raw') }}               AS invoice_date,
        {{ parse_date('due_date_raw') }}                   AS due_date,
        {{ parse_date('paid_at_raw') }}                    AS paid_at,
        LOWER(status_raw)                                 AS status,
        line_items_json,
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
                   PARTITION BY invoice_id
                   ORDER BY _ingested_at DESC, _schema_version DESC
               ) AS _row_number
        FROM cleaned
        WHERE invoice_id IS NOT NULL
    )
    WHERE _row_number = 1

)

SELECT
    invoice_id,
    customer_id,
    subscription_id,
    amount,
    currency,
    invoice_date,
    due_date,
    paid_at,
    status,
    line_items_json,
    _ingested_at,
    _schema_version
FROM deduplicated