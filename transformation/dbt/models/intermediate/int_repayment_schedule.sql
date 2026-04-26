WITH facilities AS (

    SELECT
        facility_id,
        customer_id,
        currency,
        repayment_schedule_json
    FROM {{ ref('stg_lending__credit_facilities') }}
    WHERE repayment_schedule_json IS NOT NULL
      AND repayment_schedule_json != ''

),

exploded AS (

    SELECT
        facility_id,
        customer_id,
        currency,
        UNNEST(json_extract_string(repayment_schedule_json, '$[*].due_date'))  AS installment_due_date_raw,
        UNNEST(json_extract_string(repayment_schedule_json, '$[*].amount'))    AS installment_amount_raw
    FROM facilities

)

SELECT
    facility_id,
    customer_id,
    currency,
    CAST(installment_due_date_raw AS DATE)     AS installment_due_date,
    CAST(installment_amount_raw AS DECIMAL)     AS installment_amount
FROM exploded