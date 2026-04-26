WITH approved_applications AS (

    SELECT
        customer_id,
        company_name,
        country_code,
        industry,
        headcount_at_application,
        valuation_at_application,
        arr_at_application,
        ROW_NUMBER() OVER (
            PARTITION BY customer_id
            ORDER BY application_date DESC
        ) AS rn
    FROM {{ ref('stg_lending__loan_applications') }}
    WHERE status = 'approved'

),

latest_application AS (

    SELECT
        customer_id,
        company_name,
        country_code,
        industry,
        headcount_at_application,
        valuation_at_application,
        arr_at_application
    FROM approved_applications
    WHERE rn = 1

),

active_facilities AS (

    SELECT
        customer_id,
        SUM(facility_limit) AS total_facility_limit
    FROM {{ ref('stg_lending__credit_facilities') }}
    WHERE status = 'active'
    GROUP BY customer_id

),

completed_drawdowns AS (

    SELECT
        customer_id,
        SUM(amount) AS total_drawn_amount
    FROM {{ ref('stg_lending__drawdowns') }}
    WHERE status = 'completed'
    GROUP BY customer_id

),

balance_per_currency AS (

    SELECT
        customer_id,
        currency,
        AVG(balance) AS avg_balance
    FROM {{ ref('stg_banking__account_balances') }}
    GROUP BY customer_id, currency

),

primary_currency AS (

    SELECT
        customer_id,
        currency,
        ROW_NUMBER() OVER (
            PARTITION BY customer_id
            ORDER BY avg_balance DESC
        ) AS rn
    FROM balance_per_currency

),

latest_metrics AS (

    SELECT
        customer_id,
        headcount,
        valuation,
        arr_reported,
        metric_date,
        ROW_NUMBER() OVER (
            PARTITION BY customer_id
            ORDER BY metric_date DESC
        ) AS rn
    FROM {{ ref('stg_crm__company_metrics') }}

),

prior_metrics AS (

    SELECT
        customer_id,
        headcount      AS prior_headcount,
        valuation      AS prior_valuation,
        ROW_NUMBER() OVER (
            PARTITION BY customer_id
            ORDER BY metric_date DESC
        ) AS rn
    FROM {{ ref('stg_crm__company_metrics') }}

),

latest_metric AS (

    SELECT
        customer_id,
        headcount,
        valuation,
        arr_reported
    FROM latest_metrics
    WHERE rn = 1

),

prior_metric AS (

    SELECT
        customer_id,
        prior_headcount,
        prior_valuation
    FROM prior_metrics
    WHERE rn = 2

)

SELECT
    la.customer_id,
    la.company_name,
    la.country_code,
    la.industry,
    la.headcount_at_application,
    la.valuation_at_application,
    la.arr_at_application,
    COALESCE(arr.current_arr, 0)           AS lifetime_arr,
    arr.arr_growth_pct,
    COALESCE(af.total_facility_limit, 0)   AS total_facility_limit,
    COALESCE(cd.total_drawn_amount, 0)     AS total_drawn_amount,
    pc.currency                             AS primary_account_currency,
    lm.headcount                           AS current_headcount,
    lm.valuation                           AS current_valuation,
    CASE
        WHEN pm.prior_headcount IS NULL OR pm.prior_headcount = 0 THEN NULL
        ELSE (lm.headcount - pm.prior_headcount) * 100.0 / pm.prior_headcount
    END                                    AS team_growth_pct,
    CASE
        WHEN pm.prior_valuation IS NULL OR pm.prior_valuation = 0 THEN NULL
        ELSE lm.valuation / pm.prior_valuation
    END                                    AS valuation_increase_multiple,
    CASE
        WHEN arr.current_arr IS NULL OR arr.current_arr = 0 THEN NULL
        ELSE (lm.arr_reported - arr.current_arr) * 100.0 / arr.current_arr
    END                                    AS arr_variance_pct,
    FALSE                                  AS is_orphaned
FROM latest_application la
LEFT JOIN {{ ref('int_arr_per_customer') }} arr
    ON la.customer_id = arr.customer_id
LEFT JOIN active_facilities af
    ON la.customer_id = af.customer_id
LEFT JOIN completed_drawdowns cd
    ON la.customer_id = cd.customer_id
LEFT JOIN primary_currency pc
    ON la.customer_id = pc.customer_id
    AND pc.rn = 1
LEFT JOIN latest_metric lm
    ON la.customer_id = lm.customer_id
LEFT JOIN prior_metric pm
    ON la.customer_id = pm.customer_id