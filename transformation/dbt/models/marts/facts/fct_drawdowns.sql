WITH drawdowns AS (

    SELECT
        drawdown_id,
        facility_id,
        customer_id,
        amount,
        currency,
        drawdown_date,
        purpose,
        status
    FROM {{ ref('stg_lending__drawdowns') }}

)

SELECT
    d.drawdown_id,
    d.facility_id,
    d.customer_id,
    d.amount,
    d.currency,
    d.drawdown_date,
    d.purpose,
    d.status,
    DATEDIFF('day', cf.approval_date, d.drawdown_date) AS days_since_facility_approval,
    CASE
        WHEN cf.facility_id IS NULL OR dc.customer_id IS NULL
        THEN TRUE
        ELSE FALSE
    END AS is_orphaned
FROM drawdowns d
LEFT JOIN {{ ref('dim_credit_facilities') }} cf
    ON d.facility_id = cf.facility_id
LEFT JOIN {{ ref('dim_customers') }} dc
    ON d.customer_id = dc.customer_id