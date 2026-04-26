-- Staging model: payments.subscriptions
-- Reads raw_events from S3, extracts JSON data, cleans and type-casts.

{% set source_name = 'payments' %}
{% set entity_name = 'subscriptions' %}

WITH raw AS (

    {{ read_raw_events(source_name, entity_name) }}

),

extracted AS (

    SELECT
        {{ parse_json_field('data', 'subscription_id') }}      AS subscription_id_raw,
        {{ parse_json_field('data', 'customer_id') }}          AS customer_id_raw,
        {{ parse_json_field('data', 'plan_id') }}              AS plan_id_raw,
        {{ parse_json_field('data', 'plan_name') }}            AS plan_name,
        {{ parse_json_number('data', 'mrr_amount') }}         AS mrr_amount_raw,
        {{ parse_json_field('data', 'currency') }}             AS currency_raw,
        {{ parse_json_field('data', 'status') }}               AS status_raw,
        {{ parse_json_field('data', 'billing_period_start') }} AS billing_period_start_raw,
        {{ parse_json_field('data', 'billing_period_end') }}  AS billing_period_end_raw,
        {{ parse_json_number('data', 'quantity') }}            AS quantity,
        {{ parse_json_field('data', 'created_at') }}           AS created_at_raw,
        _ingested_at,
        _schema_version,
        _batch_id

    FROM raw
    WHERE _source = '{{ source_name }}'
      AND _entity = '{{ entity_name }}'

),

cleaned AS (

    SELECT
        subscription_id_raw                                AS subscription_id,
        customer_id_raw                                    AS customer_id,
        COALESCE(plan_id_raw, 'unknown')                  AS plan_id,
        plan_name,
        {{ clean_amount('mrr_amount_raw', 'DECIMAL') }}   AS mrr_amount,
        {{ clean_currency('currency_raw') }}              AS currency,
        LOWER(status_raw)                                 AS status,
        {{ parse_date('billing_period_start_raw') }}      AS billing_period_start,
        {{ parse_date('billing_period_end_raw') }}        AS billing_period_end,
        COALESCE(TRY_CAST(quantity AS BIGINT), 1)         AS quantity,
        {{ parse_date('created_at_raw') }}                AS created_at,
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
                   PARTITION BY subscription_id
                   ORDER BY _ingested_at DESC, _schema_version DESC
               ) AS _row_number
        FROM cleaned
        WHERE subscription_id IS NOT NULL
    )
    WHERE _row_number = 1

)

SELECT
    subscription_id,
    customer_id,
    plan_id,
    plan_name,
    mrr_amount,
    currency,
    status,
    billing_period_start,
    billing_period_end,
    quantity,
    created_at,
    _ingested_at,
    _schema_version
FROM deduplicated