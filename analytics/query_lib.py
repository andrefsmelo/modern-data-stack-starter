"""Shared NL→SQL→DuckDB logic.

Used by both the CLI query tool and the Slack /query bot.
"""

from __future__ import annotations

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


def run_sql(sql: str, duckdb_path: Path | None = None) -> str:
    db_path = duckdb_path or DUCKDB_PATH
    if not db_path.exists():
        return (
            f"prod.duckdb not found at {db_path}. "
            "Build it first or set S3_BUCKET to download from S3."
        )
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        df = con.sql(sql).df()
    except Exception as exc:
        return f"SQL error: {exc}"
    finally:
        con.close()
    return df.to_string(index=False) if not df.empty else "(no rows)"


def download_duckdb_from_s3(bucket: str, region: str = "eu-west-1") -> bool:
    """Download prod.duckdb from S3. Returns True if downloaded, False if not found."""
    import subprocess

    key_id = os.environ.get("AWS_ACCESS_KEY_ID", "")
    secret = os.environ.get("AWS_SECRET_ACCESS_KEY", "")

    env = {**os.environ, "AWS_ACCESS_KEY_ID": key_id, "AWS_SECRET_ACCESS_KEY": secret, "AWS_REGION": region}

    s3_uri = f"s3://{bucket}/state/prod.duckdb"
    result = subprocess.run(
        ["aws", "s3", "ls", s3_uri],
        capture_output=True,
        env=env,
    )
    if result.returncode != 0:
        return False

    DUCKDB_PATH.parent.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        ["aws", "s3", "cp", s3_uri, str(DUCKDB_PATH)],
        capture_output=True,
        env=env,
    )
    return result.returncode == 0