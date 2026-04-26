WITH facilities AS (

    SELECT
        facility_id,
        customer_id,
        facility_limit,
        currency,
        status
    FROM {{ ref('stg_lending__credit_facilities') }}

),

completed_drawdowns AS (

    SELECT
        facility_id,
        SUM(amount) AS total_drawn_amount
    FROM {{ ref('stg_lending__drawdowns') }}
    WHERE status = 'completed'
    GROUP BY facility_id

),

all_facility_ids AS (

    SELECT facility_id FROM facilities
    UNION
    SELECT facility_id FROM completed_drawdowns

)

SELECT
    a.facility_id,
    f.customer_id,
    f.facility_limit,
    f.currency,
    f.status                                AS facility_status,
    COALESCE(d.total_drawn_amount, 0)      AS total_drawn_amount,
    CASE
        WHEN COALESCE(f.facility_limit, 0) = 0 THEN NULL
        ELSE COALESCE(d.total_drawn_amount, 0) / f.facility_limit * 100
    END                                     AS current_utilization_pct,
    CASE WHEN f.facility_id IS NULL THEN TRUE ELSE FALSE END AS is_orphaned
FROM all_facility_ids a
LEFT JOIN facilities f
    ON a.facility_id = f.facility_id
LEFT JOIN completed_drawdowns d
    ON a.facility_id = d.facility_id