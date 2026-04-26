{% macro read_raw_events(source_name, entity_name) %}

{% set s3_bucket = env_var('S3_BUCKET', 'modern-data-stack-starter') %}
{% set s3_prefix = env_var('S3_RAW_PREFIX', 'raw') %}

SELECT
    _source,
    _entity,
    _ingested_at,
    _schema_version,
    _batch_id,
    data
FROM read_parquet(
    's3://{{ s3_bucket }}/{{ s3_prefix }}/raw_events/year=*/month=*/day=*/raw_events_{{ source_name }}_{{ entity_name }}_*.parquet',
    union_by_name=true
)
WHERE data IS NOT NULL
  AND data != ''

{% endmacro %}


{% macro parse_json_field(data_col, field_name, default_value=null) %}

{% if default_value is not none %}
COALESCE(json_extract_string({{ data_col }}, '$.{{ field_name }}'), '{{ default_value }}')
{% else %}
json_extract_string({{ data_col }}, '$.{{ field_name }}')
{% endif %}

{% endmacro %}


{% macro parse_json_number(data_col, field_name) %}

TRY_CAST(json_extract_string({{ data_col }}, '$.{{ field_name }}') AS DOUBLE)

{% endmacro %}


{% macro clean_currency(column_name) %}

CASE
    WHEN UPPER(CAST({{ column_name }} AS VARCHAR)) IN ('GBP', 'EUR', 'CHF', 'SEK', 'NOK', 'DKK', 'ISK', 'USD', 'CAD')
        THEN UPPER(CAST({{ column_name }} AS VARCHAR))
    ELSE CAST(NULL AS VARCHAR)
END

{% endmacro %}


{% macro clean_amount(column_name, target_type='DOUBLE') %}

{% if target_type == 'DECIMAL' %}
TRY_CAST({{ column_name }} AS DECIMAL(18, 2))
{% else %}
TRY_CAST({{ column_name }} AS {{ target_type }})
{% endif %}

{% endmacro %}


{% macro parse_date(column_name) %}

CASE
    WHEN TRY_CAST({{ column_name }} AS TIMESTAMP) IS NOT NULL
        THEN CAST({{ column_name }} AS TIMESTAMP)
    WHEN REGEXP_MATCHES(CAST({{ column_name }} AS VARCHAR), '^\d{4}-\d{2}-\d{2}')
        THEN TRY_CAST(SUBSTRING(CAST({{ column_name }} AS VARCHAR), 1, 10) || ' 00:00:00' AS TIMESTAMP)
    WHEN REGEXP_MATCHES(CAST({{ column_name }} AS VARCHAR), '^\d{10}$')
        THEN TRY_CAST(TO_TIMESTAMP(CAST({{ column_name }} AS BIGINT)) AS TIMESTAMP)
    ELSE CAST(NULL AS TIMESTAMP)
END

{% endmacro %}


{% macro deduplicate(source_sql, partition_by, order_by) %}

WITH ranked AS (
    SELECT *,
           ROW_NUMBER() OVER (PARTITION BY {{ partition_by }} ORDER BY {{ order_by }} DESC) AS _row_number
    FROM ({{ source_sql }})
)
SELECT * EXCLUDE (_row_number)
FROM ranked
WHERE _row_number = 1

{% endmacro %}