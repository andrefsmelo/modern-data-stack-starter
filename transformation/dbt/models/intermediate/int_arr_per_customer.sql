-- ARR is computed against the dataset's most recent ingestion timestamp
-- rather than wall-clock CURRENT_TIMESTAMP, so a stale snapshot doesn't
-- collapse every customer's ARR to zero once the data ages past 30 days.
WITH as_of AS (

    SELECT LEAST(
        CURRENT_TIMESTAMP,
        COALESCE(MAX(_ingested_at), CURRENT_TIMESTAMP)
    ) AS as_of_date
    FROM {{ ref('stg_payments__subscriptions') }}

),

active_subscriptions AS (

    SELECT
        s.customer_id,
        s.subscription_id,
        s.mrr_amount,
        s.currency,
        s.billing_period_start,
        s.billing_period_end
    FROM {{ ref('stg_payments__subscriptions') }} s
    CROSS JOIN as_of
    WHERE s.status = 'active'
      AND s.billing_period_end > as_of.as_of_date

),

fx_rates AS (

    SELECT
        base_currency,
        fx_rate_to_eur
    FROM (
        SELECT
            base_currency,
            rate AS fx_rate_to_eur,
            ROW_NUMBER() OVER (
                PARTITION BY base_currency
                ORDER BY transaction_date DESC
            ) AS rn
        FROM {{ ref('stg_banking__fx_transactions') }}
        WHERE quote_currency = 'EUR'
          AND rate IS NOT NULL
          AND rate > 0
    )
    WHERE rn = 1

),

mrr_converted AS (

    SELECT
        a.customer_id,
        a.subscription_id,
        CASE
            WHEN a.currency = 'EUR' THEN a.mrr_amount
            WHEN f.fx_rate_to_eur IS NOT NULL THEN a.mrr_amount * f.fx_rate_to_eur
            ELSE NULL
        END AS mrr_amount_eur
    FROM active_subscriptions a
    LEFT JOIN fx_rates f
        ON a.currency = f.base_currency

),

current_arr AS (

    SELECT
        customer_id,
        COALESCE(SUM(mrr_amount_eur), 0) * 12 AS current_arr,
        COUNT(*) AS subscription_count
    FROM mrr_converted
    GROUP BY customer_id

),

past_subscriptions AS (

    SELECT
        s.customer_id,
        s.subscription_id,
        s.mrr_amount,
        s.currency
    FROM {{ ref('stg_payments__subscriptions') }} s
    CROSS JOIN as_of
    WHERE s.status = 'active'
      AND s.billing_period_start <= as_of.as_of_date - INTERVAL '30' DAY
      AND s.billing_period_end > as_of.as_of_date - INTERVAL '30' DAY

),

past_mrr_converted AS (

    SELECT
        p.customer_id,
        CASE
            WHEN p.currency = 'EUR' THEN p.mrr_amount
            WHEN f.fx_rate_to_eur IS NOT NULL THEN p.mrr_amount * f.fx_rate_to_eur
            ELSE NULL
        END AS mrr_amount_eur
    FROM past_subscriptions p
    LEFT JOIN fx_rates f
        ON p.currency = f.base_currency

),

past_arr AS (

    SELECT
        customer_id,
        COALESCE(SUM(mrr_amount_eur), 0) * 12 AS past_arr
    FROM past_mrr_converted
    GROUP BY customer_id

),

earliest_mrr AS (

    SELECT
        s.customer_id,
        s.earliest_mrr_eur
    FROM (
        SELECT
            customer_id,
            CASE
                WHEN currency = 'EUR' THEN mrr_amount
                WHEN f.fx_rate_to_eur IS NOT NULL THEN mrr_amount * f.fx_rate_to_eur
                ELSE NULL
            END AS earliest_mrr_eur,
            ROW_NUMBER() OVER (
                PARTITION BY customer_id
                ORDER BY billing_period_start ASC, created_at ASC
            ) AS rn
        FROM {{ ref('stg_payments__subscriptions') }}
        LEFT JOIN fx_rates f
            ON currency = f.base_currency
        WHERE status = 'active'
    ) s
    WHERE s.rn = 1

),

all_customers AS (

    SELECT DISTINCT customer_id
    FROM {{ ref('stg_payments__subscriptions') }}

)

SELECT
    c.customer_id,
    COALESCE(cur.current_arr, 0)          AS current_arr,
    COALESCE(cur.subscription_count, 0)   AS subscription_count,
    CASE
        WHEN COALESCE(pst.past_arr, e.earliest_mrr_eur * 12) = 0 THEN NULL
        ELSE (COALESCE(cur.current_arr, 0) - COALESCE(pst.past_arr, e.earliest_mrr_eur * 12))
             / NULLIF(COALESCE(pst.past_arr, e.earliest_mrr_eur * 12), 0) * 100
    END                                    AS arr_growth_pct
FROM all_customers c
LEFT JOIN current_arr cur ON c.customer_id = cur.customer_id
LEFT JOIN past_arr pst    ON c.customer_id = pst.customer_id
LEFT JOIN earliest_mrr e  ON c.customer_id = e.customer_id