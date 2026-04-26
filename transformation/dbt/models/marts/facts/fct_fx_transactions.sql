WITH fx AS (

    SELECT
        transaction_id,
        customer_id,
        base_currency,
        quote_currency,
        base_amount,
        quote_amount,
        rate AS effective_rate,
        rate_type,
        transaction_date
    FROM {{ ref('stg_banking__fx_transactions') }}

)

SELECT
    f.transaction_id,
    f.customer_id,
    f.base_currency,
    f.quote_currency,
    f.base_currency || '/' || f.quote_currency AS currency_pair,
    f.base_amount                            AS notional_base,
    f.quote_amount                           AS notional_quote,
    f.effective_rate,
    f.rate_type,
    f.transaction_date,
    CASE WHEN dc.customer_id IS NULL THEN TRUE ELSE FALSE END AS is_orphaned
FROM fx f
LEFT JOIN {{ ref('dim_customers') }} dc
    ON f.customer_id = dc.customer_id