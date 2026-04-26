#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# export-dashboards.sh — export Metabase dashboards to JSON files
#
# Usage:
#   ./visualization/export-dashboards.sh
#
# This script connects to a running Metabase instance and exports all
# dashboards to the visualization/dashboards/ directory as JSON files.
# ---------------------------------------------------------------------------
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(git -C "$SCRIPT_DIR" rev-parse --show-toplevel)"
DASHBOARD_DIR="$REPO_ROOT/visualization/dashboards"

MB_HOST="${MB_HOST:-http://localhost:3000}"
MB_USER="${MB_USER:-admin@modern-data-stack.local}"
MB_PASS="${MB_PASS:-Metabase123!}"

mkdir -p "$DASHBOARD_DIR"

SESSION_TOKEN=$(curl -sf "$MB_HOST/api/session" \
    -H "Content-Type: application/json" \
    -d "{\"username\": \"$MB_USER\", \"password\": \"$MB_PASS\"}" | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])")

echo "==> Fetching dashboards from Metabase..."
DASHBOARD_IDS=$(curl -sf "$MB_HOST/api/dashboard" \
    -H "X-Metabase-Session: $SESSION_TOKEN" | python3 -c "
import sys, json
dashboards = json.load(sys.stdin)
for d in dashboards:
    print(d['id'])
")

for DASHBOARD_ID in $DASHBOARD_IDS; do
    DASHBOARD_NAME=$(curl -sf "$MB_HOST/api/dashboard/$DASHBOARD_ID" \
        -H "X-Metabase-Session: $SESSION_TOKEN" | python3 -c "
import sys, json
d = json.load(sys.stdin)
slug = d.get('slug', d.get('name', 'dashboard')).lower().replace(' ', '-')
print(slug)
")
    OUTPUT_FILE="$DASHBOARD_DIR/${DASHBOARD_NAME}.json"
    curl -sf "$MB_HOST/api/dashboard/$DASHBOARD_ID" \
        -H "X-Metabase-Session: $SESSION_TOKEN" \
        -o "$OUTPUT_FILE"
    echo "    Exported: $DASHBOARD_NAME (id: $DASHBOARD_ID)"
done

echo "==> Done. Dashboards exported to $DASHBOARD_DIR/"