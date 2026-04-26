WITH repayments AS (

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
        status
    FROM {{ ref('stg_lending__repayments') }}

)

SELECT
    r.repayment_id,
    r.drawdown_id,
    r.facility_id,
    r.customer_id,
    r.scheduled_amount,
    r.actual_amount,
    r.currency,
    r.due_date,
    r.actual_date,
    DATEDIFF('day', r.due_date, r.actual_date) AS scheduled_vs_actual_lag_days,
    r.status,
    CASE
        WHEN cf.facility_id IS NULL OR dc.customer_id IS NULL
        THEN TRUE
        ELSE FALSE
    END AS is_orphaned
FROM repayments r
LEFT JOIN {{ ref('dim_credit_facilities') }} cf
    ON r.facility_id = cf.facility_id
LEFT JOIN {{ ref('dim_customers') }} dc
    ON r.customer_id = dc.customer_id