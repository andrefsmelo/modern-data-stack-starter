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

from query_lib import DUCKDB_PATH, question_to_sql, run_sql


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