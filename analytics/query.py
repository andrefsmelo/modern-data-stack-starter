#!/usr/bin/env python3
"""Natural-language → SQL → result against prod.duckdb.

Loads the marts (and intermediate / staging) schema descriptions from each
schema.yml, sends the user's question + that schema to Claude, runs the
SQL it returns against prod.duckdb, and prints the result.

Usage:
    python analytics/query.py "Top 10 customers by ARR"
    python analytics/query.py --show-sql "Drawdowns by month last year"
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import duckdb
import yaml
from anthropic import Anthropic

REPO_ROOT = Path(__file__).resolve().parent.parent
MODELS_DIR = REPO_ROOT / "transformation" / "dbt" / "models"
DUCKDB_PATH = REPO_ROOT / "transformation" / "dbt" / "prod.duckdb"
MODEL = "claude-sonnet-4-6"

LAYER_TO_SCHEMA = {
    "marts": "main_marts",
    "intermediate": "main_intermediate",
    "staging": "main_staging",
}


def build_schema_context() -> str:
    parts: list[str] = []
    for layer, schema in LAYER_TO_SCHEMA.items():
        layer_dir = MODELS_DIR / layer
        for yml in sorted(layer_dir.rglob("*.yml")):
            data = yaml.safe_load(yml.read_text()) or {}
            for model in data.get("models", []):
                table = f"{schema}.{model['name']}"
                parts.append(f"\nTable: {table}")
                if model.get("description"):
                    parts.append(f"  Purpose: {model['description']}")
                for col in model.get("columns", []):
                    desc = col.get("description", "").strip()
                    parts.append(f"  - {col['name']}: {desc}")
    return "\n".join(parts)


SYSTEM_TEMPLATE = """You are a data analyst answering questions about a fintech dbt warehouse stored in DuckDB.

Schema (read carefully):
{schema}

Rules:
1. Reply with a single DuckDB SQL query. No prose, no markdown fences, no comments.
2. Use fully-qualified names (schema.table).
3. Prefer marts (main_marts.*). Fall back to intermediate or staging only when no mart fits.
4. When aggregating fact tables, filter `is_orphaned = FALSE`.
5. Use DuckDB date syntax: date_trunc, INTERVAL N MONTH, current_date.
"""


def question_to_sql(question: str) -> str:
    client = Anthropic()
    schema = build_schema_context()
    msg = client.messages.create(
        model=MODEL,
        max_tokens=1024,
        system=[
            {
                "type": "text",
                "text": SYSTEM_TEMPLATE.format(schema=schema),
                "cache_control": {"type": "ephemeral"},
            },
        ],
        messages=[{"role": "user", "content": question}],
    )
    sql = msg.content[0].text.strip()
    if sql.startswith("```"):
        sql = sql.split("\n", 1)[1]
        if sql.endswith("```"):
            sql = sql[: -3]
        sql = sql.strip()
    return sql


def run_sql(sql: str) -> str:
    if not DUCKDB_PATH.exists():
        sys.exit(
            f"prod.duckdb not found at {DUCKDB_PATH}. "
            "Build it first: cd transformation/dbt && dbt build"
        )
    con = duckdb.connect(str(DUCKDB_PATH), read_only=True)
    try:
        df = con.sql(sql).df()
    finally:
        con.close()
    return df.to_string(index=False) if not df.empty else "(no rows)"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Ask the warehouse a natural-language question; Claude writes the SQL."
    )
    parser.add_argument("question", help="e.g. 'Top 10 customers by ARR'")
    parser.add_argument("--show-sql", action="store_true", help="Print SQL before running.")
    args = parser.parse_args()

    if not os.environ.get("ANTHROPIC_API_KEY"):
        sys.exit("ANTHROPIC_API_KEY is not set. Export it or add to .env.")

    sql = question_to_sql(args.question)
    if args.show_sql:
        print("--- SQL ---")
        print(sql)
        print("--- result ---")
    print(run_sql(sql))


if __name__ == "__main__":
    main()
