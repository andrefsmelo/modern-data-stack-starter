#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# setup.sh — build prod.duckdb, start Metabase, and provision dashboards
#
# Usage:
#   ./visualization/setup.sh
#
# Prerequisites:
#   - Docker + Docker Compose
#   - .env populated (copy from .env.example)
#   - dbt installed in .venv (pip install -r requirements.txt)
#
# The script:
#   1. Runs dbt against prod.duckdb (creates/updates mart tables)
#   2. Copies prod.duckdb to Metabase mount path
#   3. Starts Metabase via Docker Compose
#   4. Provisions the DuckDB database connection via Metabase API
#   5. Imports dashboard JSON exports
# ---------------------------------------------------------------------------
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(git -C "$SCRIPT_DIR" rev-parse --show-toplevel)"

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
DUCKDB_PATH="${DUCKDB_PATH:-$REPO_ROOT/transformation/dbt/prod.duckdb}"
MB_HOST="${MB_HOST:-http://localhost:3000}"
MB_PORT="${MB_PORT:-3000}"
MB_USER="${MB_USER:-admin@modern-data-stack.local}"
MB_PASS="${MB_PASS:-Metabase123!}"

export COMPOSE_FILE="$REPO_ROOT/docker-compose.yml"
export DUCKDB_PATH

cd "$REPO_ROOT"

# ---------------------------------------------------------------------------
# Step 1: Build prod.duckdb if it doesn't exist
# ---------------------------------------------------------------------------
if [[ ! -f "$DUCKDB_PATH" ]]; then
    echo "==> Building prod.duckdb via dbt..."
    set -a; source .env; set +a; unset AWS_PROFILE
    cd "$REPO_ROOT/transformation/dbt"
    DBT_DUCKDB_PATH=prod.duckdb ../../.venv/bin/dbt run --profiles-dir . --target prod
    DBT_DUCKDB_PATH=prod.duckdb ../../.venv/bin/dbt test --profiles-dir . --target prod
    cd "$REPO_ROOT"
    echo "    prod.duckdb built successfully."
else
    echo "==> prod.duckdb already exists, skipping dbt build."
    echo "    To rebuild, delete it first: rm $DUCKDB_PATH"
fi

# ---------------------------------------------------------------------------
# Step 2: Download DuckDB Metabase driver if not present
# ---------------------------------------------------------------------------
PLUGIN_DIR="$REPO_ROOT/plugins"
DUCKDB_DRIVER="$PLUGIN_DIR/duckdb.metabase-driver.jar"
if [[ ! -f "$DUCKDB_DRIVER" ]]; then
    echo "==> Downloading Metabase DuckDB driver..."
    mkdir -p "$PLUGIN_DIR"
    DUCKDB_DRIVER_VERSION="1.2.1"
    curl -LfSs -o "$DUCKDB_DRIVER" \
        "https://github.com/AlexR2D2/metabase-duckdb-driver/releases/download/v${DUCKDB_DRIVER_VERSION}/duckdb.metabase-driver.jar"
    echo "    DuckDB driver downloaded."
else
    echo "==> DuckDB driver already present."
fi

# ---------------------------------------------------------------------------
# Step 3: Start Metabase
# ---------------------------------------------------------------------------
echo "==> Starting Metabase..."
docker compose up -d

echo "    Waiting for Metabase to become healthy..."
MAX_WAIT=180
WAITED=0
while ! curl -sf "$MB_HOST/api/health" > /dev/null 2>&1; do
    sleep 5
    WAITED=$((WAITED + 5))
    if [[ $WAITED -ge $MAX_WAIT ]]; then
        echo "ERROR: Metabase did not become healthy within ${MAX_WAIT}s" >&2
        docker compose logs --tail=30 metabase
        exit 1
    fi
done
echo "    Metabase is healthy."

# ---------------------------------------------------------------------------
# Step 4: Setup (first run) or login
# ---------------------------------------------------------------------------
TOKEN_FILE="$REPO_ROOT/.metabase-session-token"

get_session_token() {
    local token
    token=$(curl -sf "$MB_HOST/api/session" \
        -H "Content-Type: application/json" \
        -d "{\"username\": \"$MB_USER\", \"password\": \"$MB_PASS\"}" | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])")
    echo "$token"
}

setup_or_login() {
    local setup_token
    setup_token=$(curl -sf "$MB_HOST/api/setup/admin_checklist" | python3 -c "
import sys, json
data = json.load(sys.stdin)
for item in data:
    if item.get('name') == 'setup' and not item.get('is_complete', True):
        print('needs_setup')
        sys.exit(0)
print('already_setup')
" 2>/dev/null || echo "needs_setup")

    if [[ "$setup_token" == "needs_setup" ]]; then
        echo "==> Setting up Metabase admin account..."
        SETUP_TOKEN=$(curl -sf "$MB_HOST/api/setup/admin_checklist" | python3 -c "
import sys, json
for item in json.load(sys.stdin):
    for step in item.get('steps', []):
        if step.get('name') == 'admin' and not step.get('is_complete', True):
            print(step.get('token', ''))
            sys.exit(0)
")
        curl -sf "$MB_HOST/api/setup" \
            -H "Content-Type: application/json" \
            -d "{
                \"token\": \"$SETUP_TOKEN\",
                \"user\": {
                    \"email\": \"$MB_USER\",
                    \"password\": \"$MB_PASS\",
                    \"first_name\": \"Admin\",
                    \"last_name\": \"User\",
                    \"site_name\": \"Modern Data Stack\"
                },
                \"prefs\": {
                    \"site_name\": \"Modern Data Stack\",
                    \"site_locale\": \"en\",
                    \"allow_tracking\": false
                }
            }" > /dev/null
        echo "    Admin account created."
    else
        echo "==> Metabase already set up, logging in..."
    fi
}

setup_or_login
SESSION_TOKEN=$(get_session_token)
echo "$SESSION_TOKEN" > "$TOKEN_FILE"

# ---------------------------------------------------------------------------
# Step 5: Add DuckDB database connection
# ---------------------------------------------------------------------------
DB_NAME="${DB_NAME:-Modern Data Stack - Prod}"

echo "==> Adding DuckDB database connection..."
EXISTING_DB=$(curl -sf "$MB_HOST/api/database" \
    -H "X-Metabase-Session: $SESSION_TOKEN" | python3 -c "
import sys, json
dbs = json.load(sys.stdin).get('data', [])
for db in dbs:
    if db.get('name') == '$DB_NAME':
        print(db['id'])
        sys.exit(0)
print('')
")

if [[ -z "$EXISTING_DB" ]]; then
    curl -sf "$MB_HOST/api/database" \
        -H "X-Metabase-Session: $SESSION_TOKEN" \
        -H "Content-Type: application/json" \
        -d "{
            \"engine\": \"duckdb\",
            \"name\": \"$DB_NAME\",
            \"details\": {
                \"db\": \"/data/prod.duckdb\"
            },
            \"is_full_sync\": true
        }" > /dev/null
    echo "    Database connection added."
else
    echo "    Database connection already exists (id: $EXISTING_DB), skipping."
fi

# ---------------------------------------------------------------------------
# Step 6: Import dashboards
# ---------------------------------------------------------------------------
DASHBOARD_DIR="$REPO_ROOT/visualization/dashboards"
if [[ -d "$DASHBOARD_DIR" && "$(ls -A "$DASHBOARD_DIR" 2>/dev/null)" ]]; then
    echo "==> Importing dashboards..."
    for dashboard_file in "$DASHBOARD_DIR"/*.json; do
        echo "    Importing: $(basename "$dashboard_file")"
        curl -sf "$MB_HOST/api/dashboard/import" \
            -H "X-Metabase-Session: $SESSION_TOKEN" \
            -F "file=@$dashboard_file" > /dev/null 2>&1 || echo "    WARNING: Failed to import $(basename "$dashboard_file")"
    done
    echo "    Dashboards imported."
else
    echo "==> No dashboard exports found in $DASHBOARD_DIR, skipping."
fi

# ---------------------------------------------------------------------------
# Done
# ---------------------------------------------------------------------------
echo ""
echo "==> Metabase is running at $MB_HOST"
echo "    Login: $MB_USER / $MB_PASS"
echo "    Database: $DB_NAME"
echo ""
echo "    To stop:  docker compose down"
echo "    To rebuild: rm $DUCKDB_PATH && ./visualization/setup.sh"