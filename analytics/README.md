# Analytics

Natural-language query helper for `prod.duckdb`. Send a question, get a result back.

## How it works

```
 your question                                    Claude              SQL          DuckDB              DataFrame
 (English)              ───►  build_schema_   ───► (Sonnet 4.6, ───►  string  ───►  read-only      ───► to stdout / Slack
                               context()            schema             that          (prod.duckdb)
 transformation/dbt/    ───►  18 tables,            cached as        runs against
 models/**/schema.yml         ~16 KB                system prompt)
```

1. Read every `schema.yml` under `transformation/dbt/models/` — table names, column names, dbt descriptions for marts, intermediate, and staging layers.
2. Send that schema + your question to Claude (Sonnet 4.6). The schema block is marked for [prompt caching](https://docs.claude.com/en/docs/build-with-claude/prompt-caching), so repeat questions in the same session reuse the cached context (~80 % cost reduction after the first call).
3. Run the returned SQL against `prod.duckdb` in **read-only mode**.
4. Print the result with `pandas.DataFrame.to_string`.

## Two interfaces

| Interface | File | When to use |
|-----------|------|-------------|
| **CLI** | `analytics/query.py` | Local development, ad-hoc queries, scripting |
| **Slack** | `analytics/slack_bot.py` | Team access, no terminal needed, on-the-fly queries from any device |

Both share the same `analytics/query_lib.py` — NL→SQL mapping, Claude prompt, DuckDB execution.

---

## CLI: `query.py`

### Setup

```bash
uv pip install anthropic duckdb pyyaml pandas

export ANTHROPIC_API_KEY=sk-ant-...   # or add to .env
```

`prod.duckdb` must already exist in `transformation/dbt/`. Two ways to get it there:

- **Pull from S3** (recommended for consumers): `aws s3 cp "s3://${S3_BUCKET}/state/prod.duckdb" transformation/dbt/prod.duckdb`. The [`dbt-build` workflow](../.github/workflows/dbt-build.yml) refreshes that object every 6 hours.
- **Build it yourself** with `dbt build` — see the [setup guide](../docs/setup.md). Needed only if you don't have a CI run yet or are testing model changes.

### Use it

```bash
python analytics/query.py "Top 10 customers by ARR"
python analytics/query.py --show-sql "Drawdowns by month over the last year"
```

`--show-sql` prints the SQL Claude generated before showing the result — useful for sanity-checking and learning the schema.

### Example questions to try

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

### What the model gets right (and where it stumbles)

The script's quality is bounded by the descriptions in `schema.yml`. Things it handles well:

- Picks marts over staging when both could answer the question.
- Applies `is_orphaned = FALSE` automatically on fact-table aggregates (it's a rule in the system prompt).
- Uses DuckDB-flavored date syntax: `date_trunc`, `INTERVAL N MONTH`, `current_date`.
- Uses fully-qualified names (`main_marts.dim_customers`).

Things to watch for:

- If a column has a vague description, the model may pick a different (also-plausible) column. Improve the description in `schema.yml` and the next call will be sharper.
- Multi-step analysis (e.g. "build a cohort table, then compute retention by month") is better written by hand — see [`docs/marts.md`](../docs/marts.md) for SQL patterns.
- The model can occasionally miss schema details when the question implies a table that doesn't exist (e.g. asking about churn when no churn fact is modelled). Run with `--show-sql` to catch this; the SQL will read fine but reference something fictitious.

---

## Slack bot: `slack_bot.py`

A local process that connects to Slack via Socket Mode (no public URL, no server). Team members type `/query <question>` in any channel the bot is in and get results inline.

### How it works

```
Slack user types: /query Top 10 customers by ARR
  → Slack sends event via WebSocket (Socket Mode)
    → slack_bot.py (local process)
      → Claude API: NL → SQL (same schema context as CLI)
        → DuckDB: runs SQL against prod.duckdb
          → Result formatted as Slack blocks and posted back
```

On startup, the bot downloads `prod.duckdb` from S3 (if `S3_BUCKET` is set) or uses the local copy.

### One-time Slack App setup (~5 minutes)

1. Go to https://api.slack.com/apps → **Create New App** → **From scratch**.
2. Name it (e.g. `data-query-bot`), pick your workspace → **Create App**.
3. **Socket Mode** → Enable → copy the **App-Level Token** (starts with `xapp-`). This is `SLACK_APP_TOKEN`.
4. **OAuth & Permissions** → add these Bot Token Scopes:
   - `chat:write`
   - `commands`
5. **Install to Workspace** → copy the **Bot User OAuth Token** (starts with `xoxb-`). This is `SLACK_BOT_TOKEN`.
6. **Slash Commands** → Create New Command:
   - Command: `/query`
   - Request URL: `https://placeholder` (Socket Mode handles it; the URL is unused but required)
   - Short description: `Ask a natural-language question about the data warehouse`
7. In Slack, invite the bot to a channel: `/invite @data-query-bot`.

### Running the bot

```bash
# Add tokens to .env or export them
set -a; source .env; set +a

# Install dependencies (if not already installed)
uv pip install slack_bolt slack_sdk anthropic duckdb pyyaml pandas

# Start the bot
python analytics/slack_bot.py
```

Output:
```
==> Using .../prod.duckdb (XX.X MB)
==> Starting Slack bot (Socket Mode)...
⚡ Bolt app is running!
```

Now type `/query Top 10 customers by ARR` in Slack. The bot will:
1. Acknowledge with "Running query..."
2. Send the question to Claude to generate SQL
3. Run the SQL against DuckDB
4. Post the result as formatted Slack blocks (question + SQL + result)

**Error handling:** If the SQL fails, the bot posts the generated SQL and the error message so you can debug.

### Stopping the bot

`Ctrl+C` — zero cost when not running.

### Cost

| Component | Cost |
|-----------|------|
| Slack Bot | $0 (free plan) |
| DuckDB | $0 |
| Claude API | ~1¢/query (cold cache), ~0.1¢/query (warm) |

---

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