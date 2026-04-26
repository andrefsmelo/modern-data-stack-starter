WITH facilities AS (

    SELECT
        facility_id,
        application_id,
        customer_id,
        facility_limit,
        currency,
        approval_date,
        maturity_date,
        status,
        interest_rate
    FROM {{ ref('stg_lending__credit_facilities') }}

),

dim_customers AS (

    SELECT customer_id
    FROM {{ ref('dim_customers') }}

)

SELECT
    f.facility_id,
    f.application_id,
    f.customer_id,
    f.facility_limit,
    f.currency,
    f.approval_date,
    f.maturity_date,
    f.status                                AS facility_status,
    f.interest_rate,
    u.current_utilization_pct,
    CASE WHEN dc.customer_id IS NULL THEN TRUE ELSE FALSE END AS is_orphaned
FROM facilities f
LEFT JOIN {{ ref('int_facility_utilization') }} u
    ON f.facility_id = u.facility_id
LEFT JOIN dim_customers dc
    ON f.customer_id = dc.customer_id