#!/usr/bin/env bash
set -euo pipefail

# Generate synthetic dummy data and sync it to S3.
#
# Usage:
#   BUCKET=float-data-prod ./ingestion/scripts/push_to_s3.sh
#
# Environment variables:
#   BUCKET      (required) S3 bucket name, e.g. float-data-prod
#   SEED        (optional) Random seed for reproducibility. Default: 42
#   DAYS        (optional) Number of days to generate. Default: 30
#   START_DATE  (optional) Start date in YYYY-MM-DD. Default: 2026-01-01
#   OUTPUT_DIR  (optional) Local staging folder. Default: ./data
#   AWS_REGION  (optional) AWS region. Default: eu-west-1
#
# Example with overrides:
#   BUCKET=float-data-dev SEED=123 DAYS=7 ./ingestion/scripts/push_to_s3.sh

SEED="${SEED:-42}"
DAYS="${DAYS:-30}"
START_DATE="${START_DATE:-2026-01-01}"
OUTPUT_DIR="${OUTPUT_DIR:-./data}"
AWS_REGION="${AWS_REGION:-eu-west-1}"

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
    --days "$DAYS"

# ---------------------------------------------------------------------------
# Step 2: Validate local structure
# ---------------------------------------------------------------------------

echo "==> Verifying output structure..."

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
        echo "  WARNING: Missing entity folder: $entity"
        missing=$((missing + 1))
    fi
done

if [[ $missing -gt 0 ]]; then
    echo "ERROR: $missing entity folder(s) missing. Aborting sync."
    exit 1
fi

total_files=$(find "$OUTPUT_DIR" -name "*.parquet" | wc -l)
echo "  Found $total_files Parquet files in $OUTPUT_DIR"

# ---------------------------------------------------------------------------
# Step 3: Sync to S3
# ---------------------------------------------------------------------------

echo "==> Syncing to s3://$BUCKET/raw/ (region: $AWS_REGION)..."

aws s3 sync "$OUTPUT_DIR" "s3://$BUCKET/raw/" \
    --region "$AWS_REGION" \
    --delete

# ---------------------------------------------------------------------------
# Step 4: Verify S3 upload
# ---------------------------------------------------------------------------

echo "==> Verifying S3 upload..."

total_objects=$(aws s3 ls "s3://$BUCKET/raw/" --recursive --region "$AWS_REGION" | wc -l)
echo "  Total objects in s3://$BUCKET/raw/: $total_objects"

# Quick sanity check: list one file per entity
for entity in "${expected_entities[@]}"; do
    sample=$(aws s3 ls "s3://$BUCKET/raw/$entity/" --recursive --region "$AWS_REGION" | head -1)
    if [[ -n "$sample" ]]; then
        echo "  ✓ $entity: $sample"
    else
        echo "  ✗ $entity: NO FILES FOUND"
    fi
done

echo "==> Done."
