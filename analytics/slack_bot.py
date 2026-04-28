#!/usr/bin/env python3
"""Slack /query bot — natural-language data queries from Slack.

Connects via Socket Mode (no public URL needed). On startup, downloads
prod.duckdb from S3 (if configured) or uses the local copy.

Usage:
    set -a; source .env; set +a
    python analytics/slack_bot.py

Required env vars:
    SLACK_BOT_TOKEN   xoxb-...  (Bot User OAuth Token)
    SLACK_APP_TOKEN   xapp-...  (Socket Mode token)
    ANTHROPIC_API_KEY sk-ant-... (Claude API key)

Optional:
    S3_BUCKET         download prod.duckdb from S3 on startup
    AWS_REGION        defaults to eu-west-1
    AWS_ACCESS_KEY_ID + AWS_SECRET_ACCESS_KEY  (if downloading from S3)
"""

from __future__ import annotations

import os
import sys
import textwrap

from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

from query_lib import DUCKDB_PATH, download_duckdb_from_s3, question_to_sql, run_sql

MAX_BLOCKS = 50
MAX_TEXT_LEN = 2900


def _truncate(text: str, max_len: int = MAX_TEXT_LEN) -> str:
    if len(text) <= max_len:
        return text
    return text[:max_len] + "\n... (truncated)"


def _format_result(question: str, sql: str, result: str) -> list[dict]:
    """Build Slack blocks for a successful query result."""
    header = {
        "type": "section",
        "text": {"type": "mrkdwn", "text": f"*Query:* {_truncate(question, 200)}"},
    }

    sql_block = {
        "type": "section",
        "text": {
            "type": "mrkdwn",
            "text": f"```sql\n{_truncate(sql, MAX_TEXT_LEN - 10)}\n```",
        },
    }

    result_text = _truncate(result, MAX_TEXT_LEN)
    result_block = {
        "type": "section",
        "text": {"type": "mrkdwn", "text": f"```{result_text}```"},
    }

    blocks = [header, sql_block, result_block]
    return blocks[:MAX_BLOCKS]


def _format_error(question: str, sql: str, error: str) -> list[dict]:
    """Build Slack blocks for a failed query."""
    header = {
        "type": "section",
        "text": {"type": "mrkdwn", "text": f":x: *Query failed:* {_truncate(question, 200)}"},
    }

    sql_block = {
        "type": "section",
        "text": {
            "type": "mrkdwn",
            "text": f"```sql\n{_truncate(sql, MAX_TEXT_LEN - 10)}\n```",
        },
    }

    error_block = {
        "type": "section",
        "text": {"type": "mrkdwn", "text": f"```{_truncate(error, 500)}```"},
    }

    return [header, sql_block, error_block][:MAX_BLOCKS]


app = App(token=os.environ.get("SLACK_BOT_TOKEN"))


@app.command("/query")
def handle_query(ack, respond, command):
    ack()
    question = command["text"].strip()
    if not question:
        respond("Please provide a question, e.g. `/query Top 10 customers by ARR`")
        return

    respond(text=f":hourglass: Running query: *{question[:200]}*")

    try:
        sql = question_to_sql(question)
        result = run_sql(sql)
        if result.startswith("SQL error:") or result.startswith("prod.duckdb not found"):
            blocks = _format_error(question, sql, result)
            respond(text="Query failed.", blocks=blocks)
        else:
            blocks = _format_result(question, sql, result)
            respond(text="Query succeeded.", blocks=blocks)
    except Exception as exc:
        respond(text=f":x: Unexpected error: {exc}")


def main() -> None:
    missing = []
    for var in ("SLACK_BOT_TOKEN", "SLACK_APP_TOKEN", "ANTHROPIC_API_KEY"):
        if not os.environ.get(var):
            missing.append(var)
    if missing:
        sys.exit(f"Missing env vars: {', '.join(missing)}. Add them to .env or export them.")

    bucket = os.environ.get("S3_BUCKET")
    if bucket and not DUCKDB_PATH.exists():
        region = os.environ.get("AWS_REGION", "eu-west-1")
        print(f"==> Downloading prod.duckdb from s3://{bucket}/state/ ...")
        if download_duckdb_from_s3(bucket, region):
            print(f"==> Downloaded prod.duckdb ({DUCKDB_PATH.stat().st_size / 1e6:.1f} MB)")
        else:
            print(f"==> No prod.duckdb found in S3. Will use local copy if available.")

    if DUCKDB_PATH.exists():
        print(f"==> Using {DUCKDB_PATH} ({DUCKDB_PATH.stat().st_size / 1e6:.1f} MB)")
    else:
        print(f"==> WARNING: {DUCKDB_PATH} not found. Queries will fail until dbt build runs.")

    print("==> Starting Slack bot (Socket Mode)...")
    handler = SocketModeHandler(app, os.environ["SLACK_APP_TOKEN"])
    handler.start()


if __name__ == "__main__":
    main()