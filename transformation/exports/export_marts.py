#!/usr/bin/env python3
"""Export every dbt mart from prod.duckdb to S3 as Parquet.

Run after `dbt build` succeeds. Writes directly to S3 via DuckDB's httpfs
extension — no intermediate local Parquet file is produced.

Output layout:
    s3://${S3_BUCKET}/marts/<table_name>/<table_name>.parquet

Each run overwrites the previous file. Enable S3 object versioning on the
bucket if you need point-in-time history.

Required env vars: S3_BUCKET, AWS_REGION, AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import duckdb

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DUCKDB_PATH = REPO_ROOT / "transformation" / "dbt" / "prod.duckdb"

# If you add a mart, add it here.
MARTS = [
    "dim_customers",
    "dim_credit_facilities",
    "fct_drawdowns",
    "fct_repayments",
    "fct_fx_transactions",
]


def main() -> None:
    bucket = os.environ.get("S3_BUCKET")
    region = os.environ.get("AWS_REGION", "eu-west-1")
    key_id = os.environ.get("AWS_ACCESS_KEY_ID")
    secret = os.environ.get("AWS_SECRET_ACCESS_KEY")

    if not bucket:
        sys.exit("ERROR: S3_BUCKET is not set.")
    if not (key_id and secret):
        sys.exit("ERROR: AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY must be set.")
    if not DUCKDB_PATH.exists():
        sys.exit(f"ERROR: {DUCKDB_PATH} not found. Run `dbt build` first.")

    con = duckdb.connect(str(DUCKDB_PATH), read_only=True)
    con.execute("INSTALL httpfs; LOAD httpfs;")
    con.execute(f"SET s3_region = '{region}'")
    con.execute(f"SET s3_access_key_id = '{key_id}'")
    con.execute(f"SET s3_secret_access_key = '{secret}'")

    for table in MARTS:
        target = f"s3://{bucket}/marts/{table}/{table}.parquet"
        print(f"==> Exporting main_marts.{table} -> {target}", flush=True)
        con.execute(
            f"COPY (SELECT * FROM main_marts.{table}) "
            f"TO '{target}' (FORMAT PARQUET, OVERWRITE_OR_IGNORE)"
        )
        rows = con.execute(f"SELECT COUNT(*) FROM main_marts.{table}").fetchone()[0]
        print(f"    {rows} rows exported.", flush=True)

    con.close()
    print("==> All marts exported.")


if __name__ == "__main__":
    main()
