# Analytics

Natural-language query helper for `prod.duckdb`. Send a question, get a result back.

## How it works

```
 your question                                    Claude              SQL          DuckDB              DataFrame
 (English)              ───►  build_schema_   ───► (Sonnet 4.6, ───►  string  ───►  read-only      ───► to stdout
                              context()            schema             that          (prod.duckdb)
 transformation/dbt/    ───►  18 tables,            cached as        runs against
 models/**/schema.yml         ~16 KB                system prompt)
```

1. Read every `schema.yml` under `transformation/dbt/models/` — table names, column names, dbt descriptions for marts, intermediate, and staging layers.
2. Send that schema + your question to Claude (Sonnet 4.6). The schema block is marked for [prompt caching](https://docs.claude.com/en/docs/build-with-claude/prompt-caching), so repeat questions in the same session reuse the cached context (~80 % cost reduction after the first call).
3. Run the returned SQL against `prod.duckdb` in **read-only mode**.
4. Print the result with `pandas.DataFrame.to_string`.

## Setup

```bash
uv pip install anthropic duckdb pyyaml pandas

export ANTHROPIC_API_KEY=sk-ant-...   # or add to .env
```

`prod.duckdb` must already exist in `transformation/dbt/`. Two ways to get it there:

- **Pull from S3** (recommended for consumers): `aws s3 cp "s3://${S3_BUCKET}/state/prod.duckdb" transformation/dbt/prod.duckdb`. The [`dbt-build` workflow](../.github/workflows/dbt-build.yml) refreshes that object every 6 hours.
- **Build it yourself** with `dbt build` — see the [setup guide](../docs/setup.md). Needed only if you don't have a CI run yet or are testing model changes.

## Use it

```bash
python analytics/query.py "Top 10 customers by ARR"
python analytics/query.py --show-sql "Drawdowns by month over the last year"
```

`--show-sql` prints the SQL Claude generated before showing the result — useful for sanity-checking and learning the schema.

## Example questions to try

| Intent | Question |
|---|---|
| Top-N | `"Top 10 customers by total drawn amount"` |
| Aggregation | `"How many active credit facilities are there and what's the total facility limit?"` |
| Time series | `"Drawdown count and total amount per month for the last 6 months"` |
| Distribution | `"Repayment lateness in 4 buckets: on time, 1-7 days late, 8-30 days late, 30+ days late"` |
| Concentration | `"What share of total facility limit is held by the top 5 customers?"` |
| Currency mix | `"Which currency pairs have the most FX volume?"` |
| Customer 360 | `"Show every drawdown for customer c0094592-09fc-431d-a751-9543c7798b9b"` |
| Data quality | `"How many orphan rows are in each fact table, as a percentage?"` |
| Comparisons | `"Which customers have the highest average repayment lag (with at least 5 scheduled repayments)?"` |
| Open-ended | `"Are there any customers whose total drawn exceeds their facility limit?"` |

## Worked examples (real output)

### 1. Simple aggregation — "How many active credit facilities are over 100% utilized?"

```sql
SELECT COUNT(*) AS overutilized_active_facilities
FROM main_marts.dim_credit_facilities
WHERE facility_status = 'active'
  AND is_orphaned = FALSE
  AND current_utilization_pct > 100;
```
```
 overutilized_active_facilities
                              7
```

### 2. Time series — "Drawdown count and total amount per month for the last 6 months"

```sql
SELECT date_trunc('month', drawdown_date) AS month,
       COUNT(*)                           AS drawdown_count,
       SUM(amount)                        AS total_amount
FROM main_marts.fct_drawdowns
WHERE is_orphaned = FALSE
  AND drawdown_date >= date_trunc('month', current_date - INTERVAL 5 MONTH)
GROUP BY 1 ORDER BY 1;
```
```
     month  drawdown_count  total_amount
2026-01-01             113  1.191175e+09
```

### 3. Window function — "What share of total facility limit is held by the top 3 customers?"

```sql
SELECT SUM(CASE WHEN rnk <= 3 THEN total_facility_limit ELSE 0 END)
       / SUM(total_facility_limit) * 100 AS top3_share_pct
FROM (
  SELECT customer_id, total_facility_limit,
         RANK() OVER (ORDER BY total_facility_limit DESC) AS rnk
  FROM main_marts.dim_customers
  WHERE total_facility_limit IS NOT NULL
) ranked;
```
```
 top3_share_pct
      74.598916
```

> 75 % of the book sits with three customers. In production this is the kind of concentration-risk signal that would page the credit team — answered here by typing one English sentence.

## What the model gets right (and where it stumbles)

The script's quality is bounded by the descriptions in `schema.yml`. Things it handles well:

- Picks marts over staging when both could answer the question.
- Applies `is_orphaned = FALSE` automatically on fact-table aggregates (it's a rule in the system prompt).
- Uses DuckDB-flavored date syntax: `date_trunc`, `INTERVAL N MONTH`, `current_date`.
- Uses fully-qualified names (`main_marts.dim_customers`).

Things to watch for:

- If a column has a vague description, the model may pick a different (also-plausible) column. Improve the description in `schema.yml` and the next call will be sharper.
- Multi-step analysis (e.g. "build a cohort table, then compute retention by month") is better written by hand — see [`docs/marts.md`](../docs/marts.md) for SQL patterns.
- The model can occasionally miss schema details when the question implies a table that doesn't exist (e.g. asking about churn when no churn fact is modelled). Run with `--show-sql` to catch this; the SQL will read fine but reference something fictitious.

## Costs and limits

- **Read-only by design.** `INSERT` / `UPDATE` / `DELETE` from the model are blocked at the DuckDB connection level (`read_only=True`).
- **Per-call cost** ≈ 1 ¢ on cold cache (16 KB system prompt as input), ≈ 0.1 ¢ on warm cache. The cache TTL is 5 minutes, so a session of related questions stays warm.
- **No history is sent** — each question is a fresh call. Add `messages=[…previous turns…]` if you want a follow-up to know about the prior question.

## Extending it

Reasonable next steps if you want to push this further:

- **Auto-explain:** add a second LLM call that takes the SQL + result rows and writes a one-sentence interpretation.
- **Caching the result:** memoize `(question, schema_hash) → SQL` so repeat questions skip the API entirely.
- **Charting:** if the result has 1 categorical + 1 numeric column, hand it to `plotext` or write a Streamlit wrapper. The model can already pick a `display_hint` field if you add one to the system prompt.
- **Few-shot examples:** add `messages=[{"role": "user", "content": "..."}, {"role": "assistant", "content": "..."}]` pairs to the request to anchor the model on common patterns from `docs/marts.md`.
