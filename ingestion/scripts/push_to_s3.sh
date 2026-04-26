#!/usr/bin/env bash
set -euo pipefail

# Generate synthetic dummy data and sync it to S3.
#
# Usage:
#   BUCKET=float-data-prod ./ingestion/scripts/push_to_s3.sh
#
# Configuration:
#   Copy .env.example to .env.local and fill in your values:
#     cp .env.example .env.local
#
# Environment variables (override .env.local):
#   BUCKET        (required) S3 bucket name, e.g. float-data-prod
#   SEED          (optional) Random seed for reproducibility. Default: 42
#   DAYS          (optional) Number of days to generate. Default: 30
#   START_DATE    (optional) Start date in YYYY-MM-DD. Default: 2026-01-01
#   OUTPUT_DIR    (optional) Local staging folder. Default: ./data
#   AWS_REGION    (optional) AWS region. Default: eu-west-1
#   AWS_PROFILE   (optional) AWS CLI profile name. Default: default
#   FORMAT        (optional) Output format: flat, raw_events, or both. Default: raw_events
#   ENV_FILE      (optional) Path to .env file. Default: .env.local in repo root
#
# Example with overrides:
#   BUCKET=float-data-dev SEED=123 DAYS=7 FORMAT=both ./ingestion/scripts/push_to_s3.sh

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="${ENV_FILE:-$(git -C "$SCRIPT_DIR/../.." rev-parse --show-toplevel 2>/dev/null)/.env}"
if [[ -f "$ENV_FILE" ]]; then
    set -a; source "$ENV_FILE"; set +a
fi

SEED="${SEED:-42}"
DAYS="${DAYS:-30}"
START_DATE="${START_DATE:-2026-01-01}"
OUTPUT_DIR="${OUTPUT_DIR:-./data}"
AWS_REGION="${AWS_REGION:-eu-west-1}"
FORMAT="${FORMAT:-raw_events}"
AWS_PROFILE="${AWS_PROFILE:-}"

# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

if [[ -z "${BUCKET:-}" ]]; then
    echo "ERROR: BUCKET environment variable is required."
    echo ""
    echo "Example:"
    echo "  BUCKET=float-data-prod ./ingestion/scripts/push_to_s3.sh"
    exit 1
fi

if ! command -v python3 &>/dev/null; then
    echo "ERROR: python3 is not installed."
    exit 1
fi

if ! command -v aws &>/dev/null; then
    echo "ERROR: AWS CLI is not installed. Install it from https://aws.amazon.com/cli/"
    exit 1
fi

# ---------------------------------------------------------------------------
# Step 1: Generate
# ---------------------------------------------------------------------------

echo "==> Generating dummy data (seed=$SEED, days=$DAYS, start=$START_DATE)..."
rm -rf "$OUTPUT_DIR"

python3 ingestion/scripts/generate_dummy_data.py \
    --output-dir "$OUTPUT_DIR" \
    --seed "$SEED" \
    --start-date "$START_DATE" \
    --days "$DAYS" \
    --format "$FORMAT"

# ---------------------------------------------------------------------------
# Step 2: Validate local structure
# ---------------------------------------------------------------------------

echo "==> Verifying output structure..."

if [[ "$FORMAT" == "flat" || "$FORMAT" == "both" ]]; then
    expected_entities=(
        "payments/subscriptions"
        "payments/invoices"
        "lending/loan_applications"
        "lending/credit_facilities"
        "lending/drawdowns"
        "lending/repayments"
        "banking/fx_transactions"
        "banking/account_balances"
        "crm/company_metrics"
    )

    missing=0
    for entity in "${expected_entities[@]}"; do
        if [[ ! -d "$OUTPUT_DIR/$entity" ]]; then
            echo "  WARNING: Missing flat entity folder: $entity"
            missing=$((missing + 1))
        fi
    done

    if [[ $missing -gt 0 && "$FORMAT" == "flat" ]]; then
        echo "ERROR: $missing entity folder(s) missing. Aborting sync."
        exit 1
    fi
fi

if [[ "$FORMAT" == "raw_events" || "$FORMAT" == "both" ]]; then
    if [[ ! -d "$OUTPUT_DIR/raw_events" ]]; then
        echo "ERROR: Missing raw_events folder. Aborting sync."
        exit 1
    fi
fi

# Quick sanity check: verify raw_events folder
if [[ "$FORMAT" == "raw_events" || "$FORMAT" == "both" ]]; then
    raw_count=$(find "$OUTPUT_DIR/raw_events" -name "*.parquet" | wc -l)
    echo "  Found $raw_count raw_events Parquet files"
fi

if [[ "$FORMAT" == "flat" || "$FORMAT" == "both" ]]; then
    flat_count=$(find "$OUTPUT_DIR" -path "*/raw_events" -prune -o -name "*.parquet" -print | wc -l)
    echo "  Found $flat_count flat Parquet files"
fi

# ---------------------------------------------------------------------------
# Step 3: Sync to S3
# ---------------------------------------------------------------------------

echo "==> Syncing to s3://$BUCKET/raw/ (region: $AWS_REGION)..."

aws ${AWS_PROFILE:+--profile "$AWS_PROFILE"} s3 sync "$OUTPUT_DIR" "s3://$BUCKET/raw/" \
    --region "$AWS_REGION" \
    --delete

# ---------------------------------------------------------------------------
# Step 4: Verify S3 upload
# ---------------------------------------------------------------------------

echo "==> Verifying S3 upload..."

total_objects=$(aws ${AWS_PROFILE:+--profile "$AWS_PROFILE"} s3 ls "s3://$BUCKET/raw/" --recursive --region "$AWS_REGION" | wc -l)
echo "  Total objects in s3://$BUCKET/raw/: $total_objects"

# Quick sanity check: list sample files
raw_sample=$(aws ${AWS_PROFILE:+--profile "$AWS_PROFILE"} s3 ls "s3://$BUCKET/raw/raw_events/" --recursive --region "$AWS_REGION" | head -1 || true)
if [[ -n "$raw_sample" ]]; then
    echo "  ✓ raw_events: $raw_sample"
else
    echo "  ✗ raw_events: NO FILES FOUND"
fi

echo "==> Done."
