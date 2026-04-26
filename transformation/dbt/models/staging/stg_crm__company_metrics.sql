-- Staging model: crm.company_metrics
-- Reads raw_events from S3, extracts JSON data, cleans and type-casts.

{% set source_name = 'crm' %}
{% set entity_name = 'company_metrics' %}

WITH raw AS (

    {{ read_raw_events(source_name, entity_name) }}

),

extracted AS (

    SELECT
        {{ parse_json_field('data', 'metric_id') }}         AS metric_id_raw,
        {{ parse_json_field('data', 'customer_id') }}       AS customer_id_raw,
        {{ parse_json_field('data', 'metric_date') }}        AS metric_date_raw,
        {{ parse_json_number('data', 'headcount') }}        AS headcount_raw,
        {{ parse_json_number('data', 'valuation') }}        AS valuation_raw,
        {{ parse_json_number('data', 'arr_reported') }}     AS arr_reported_raw,
        _ingested_at,
        _schema_version,
        _batch_id

    FROM raw
    WHERE _source = '{{ source_name }}'
      AND _entity = '{{ entity_name }}'

),

cleaned AS (

    SELECT
        metric_id_raw                                       AS metric_id,
        customer_id_raw                                      AS customer_id,
        {{ parse_date('metric_date_raw') }}                  AS metric_date,
        COALESCE(TRY_CAST(headcount_raw AS BIGINT), 0)      AS headcount,
        {{ clean_amount('valuation_raw', 'DECIMAL') }}       AS valuation,
        {{ clean_amount('arr_reported_raw', 'DECIMAL') }}    AS arr_reported,
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
                   PARTITION BY metric_id
                   ORDER BY _ingested_at DESC, _schema_version DESC
               ) AS _row_number
        FROM cleaned
        WHERE metric_id IS NOT NULL
    )
    WHERE _row_number = 1

)

SELECT
    metric_id,
    customer_id,
    metric_date,
    headcount,
    valuation,
    arr_reported,
    _ingested_at,
    _schema_version
FROM deduplicated