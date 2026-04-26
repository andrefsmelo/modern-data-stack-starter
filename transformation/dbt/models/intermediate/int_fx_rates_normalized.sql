WITH source AS (

    SELECT
        transaction_id,
        customer_id,
        base_currency,
        quote_currency,
        base_amount,
        quote_amount,
        rate,
        rate_type,
        transaction_date
    FROM {{ ref('stg_banking__fx_transactions') }}

),

normalized AS (

    SELECT
        transaction_id,
        customer_id,
        base_currency,
        quote_currency,
        base_currency || quote_currency                     AS currency_pair,
        base_amount,
        quote_amount,
        CASE
            WHEN rate > 10 THEN 1.0 / rate
            ELSE rate
        END                                                 AS effective_rate,
        rate_type,
        transaction_date
    FROM source

)

SELECT
    transaction_id,
    customer_id,
    base_currency,
    quote_currency,
    currency_pair,
    base_amount                                            AS base_amount,
    COALESCE(quote_amount, base_amount * effective_rate)  AS quote_amount,
    effective_rate,
    rate_type,
    transaction_date,
    FALSE                                                  AS is_orphaned
FROM normalized