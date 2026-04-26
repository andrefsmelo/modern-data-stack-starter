"""
provision_dashboards.py — Create Metabase dashboards and questions via the API.

This script connects to a running Metabase instance and creates:
  - A "Lending" collection
  - A "Payments" collection
  - A "Banking & FX" collection
  - Dashboards with relevant questions (cards) in each collection

Usage:
    python visualization/provision_dashboards.py [--host URL] [--user EMAIL] [--pass PASSWORD]

Requires: requests (pip install requests)
"""

import argparse
import json
import sys
import time
import urllib.request
import urllib.error

try:
    import requests
except ImportError:
    print("ERROR: 'requests' is required. Install with: pip install requests")
    sys.exit(1)

MB_HOST = "http://localhost:3000"
MB_USER = "admin@modern-data-stack.local"
MB_PASS = "Metabase123!"

DB_NAME = "Modern Data Stack - Prod"


def get_session(host, user, password):
    r = requests.post(
        f"{host}/api/session",
        json={"username": user, "password": password},
    )
    r.raise_for_status()
    return r.json()["id"]


def get_db_id(host, session, db_name):
    r = requests.get(f"{host}/api/database", headers={"X-Metabase-Session": session})
    r.raise_for_status()
    for db in r.json()["data"]:
        if db["name"] == db_name:
            return db["id"]
    raise ValueError(f"Database '{db_name}' not found. Available: {[d['name'] for d in r.json()['data']]}")


def get_or_create_collection(host, session, name, parent_id=None):
    r = requests.get(f"{host}/api/collection", headers={"X-Metabase-Session": session})
    r.raise_for_status()
    for c in r.json():
        if c["name"] == name and c.get("parent_id") == parent_id:
            return c["id"], c.get("slug", name.lower().replace(" ", "-"))

    payload = {"name": name, "color": "#509EE3"}
    if parent_id is not None:
        payload["parent_id"] = parent_id
    r = requests.post(
        f"{host}/api/collection",
        headers={"X-Metabase-Session": session},
        json=payload,
    )
    r.raise_for_status()
    data = r.json()
    return data["id"], data.get("slug", name.lower().replace(" ", "-"))


def create_question(host, session, db_id, name, query_sql, collection_id=None):
    payload = {
        "name": name,
        "display": "scalar",
        "dataset_query": {
            "type": "native",
            "database": db_id,
            "native": {"query": query_sql},
        },
        "visualization_settings": {},
        "collection_id": collection_id,
    }
    r = requests.post(
        f"{host}/api/card",
        headers={"X-Metabase-Session": session},
        json=payload,
    )
    r.raise_for_status()
    return r.json()["id"]


def create_question_with_display(host, session, db_id, name, query_sql, display="scalar", collection_id=None, viz_settings=None):
    payload = {
        "name": name,
        "display": display,
        "dataset_query": {
            "type": "native",
            "database": db_id,
            "native": {"query": query_sql},
        },
        "visualization_settings": viz_settings or {},
        "collection_id": collection_id,
    }
    r = requests.post(
        f"{host}/api/card",
        headers={"X-Metabase-Session": session},
        json=payload,
    )
    r.raise_for_status()
    return r.json()["id"]


def create_dashboard(host, session, name, collection_id=None):
    payload = {"name": name, "collection_id": collection_id}
    r = requests.post(
        f"{host}/api/dashboard",
        headers={"X-Metabase-Session": session},
        json=payload,
    )
    r.raise_for_status()
    data = r.json()
    return data["id"]


def add_card_to_dashboard(host, session, dashboard_id, card_id, row=0, col=0, size_x=6, size_y=4):
    r = requests.post(
        f"{host}/api/dashboard/{dashboard_id}/cards",
        headers={"X-Metabase-Session": session},
        json={
            "card_id": card_id,
            "row": row,
            "col": col,
            "size_x": size_x,
            "size_y": size_y,
        },
    )
    r.raise_for_status()
    return r.json()["id"]


def add_text_to_dashboard(host, session, dashboard_id, text, row=0, col=0, size_x=18, size_y=1):
    r = requests.post(
        f"{host}/api/dashboard/{dashboard_id}/cards",
        headers={"X-Metabase-Session": session},
        json={
            "visualization_settings": {"text": text},
            "row": row,
            "col": col,
            "size_x": size_x,
            "size_y": size_y,
        },
    )
    r.raise_for_status()
    return r.json()["id"]


def wait_for_metabase(host, timeout=180):
    start = time.time()
    while time.time() - start < timeout:
        try:
            r = requests.get(f"{host}/api/health", timeout=5)
            if r.status_code == 200:
                return True
        except requests.ConnectionError:
            pass
        time.sleep(5)
    raise TimeoutError(f"Metabase did not become healthy within {timeout}s")


def main():
    parser = argparse.ArgumentParser(description="Provision Metabase dashboards")
    parser.add_argument("--host", default=MB_HOST, help="Metabase URL")
    parser.add_argument("--user", default=MB_USER, help="Metabase admin email")
    parser.add_argument("--pass", dest="password", default=MB_PASS, help="Metabase admin password")
    parser.add_argument("--db-name", default=DB_NAME, help="DuckDB database name in Metabase")
    args = parser.parse_args()

    host = args.host
    user = args.user
    password = args.password
    db_name = args.db_name

    print(f"==> Connecting to Metabase at {host}...")
    wait_for_metabase(host)

    session = get_session(host, user, password)
    db_id = get_db_id(host, session, db_name)
    print(f"    Database ID: {db_id}")

    # ------------------------------------------------------------------
    # Create collections
    # ------------------------------------------------------------------
    print("==> Creating collections...")
    lending_coll, _ = get_or_create_collection(host, session, "Lending")
    payments_coll, _ = get_or_create_collection(host, session, "Payments")
    banking_coll, _ = get_or_create_collection(host, session, "Banking & FX")
    executive_coll, _ = get_or_create_collection(host, session, "Executive")

    # ------------------------------------------------------------------
    # Lending Dashboard
    # ------------------------------------------------------------------
    print("==> Creating Lending dashboard...")
    lending_dash = create_dashboard(host, session, "Lending Overview", lending_coll)

    add_text_to_dashboard(host, session, lending_dash, "# Lending Overview", row=0, col=0, size_y=1)

    q_total_facilities = create_question(
        host, session, db_id,
        "Total Active Facility Limit",
        "SELECT SUM(facility_limit) AS total_facility_limit FROM main_marts.dim_credit_facilities WHERE status = 'active'",
        lending_coll,
    )
    add_card_to_dashboard(host, session, lending_dash, q_total_facilities, row=1, col=0, size_x=6, size_y=4)

    q_total_drawn = create_question(
        host, session, db_id,
        "Total Drawn Amount",
        "SELECT SUM(amount) AS total_drawn FROM main_marts.fct_drawdowns WHERE is_orphaned = FALSE",
        lending_coll,
    )
    add_card_to_dashboard(host, session, lending_dash, q_total_drawn, row=1, col=6, size_x=6, size_y=4)

    q_facility_util = create_question_with_display(
        host, session, db_id,
        "Facility Utilization by Status",
        "SELECT status, COUNT(*) AS facility_count, AVG(utilization_pct) AS avg_utilization_pct FROM main_marts.dim_credit_facilities GROUP BY status ORDER BY facility_count DESC",
        display="bar",
        collection_id=lending_coll,
        viz_settings={"graph.dimensions": ["status"], "graph.metrics": ["avg_utilization_pct"]},
    )
    add_card_to_dashboard(host, session, lending_dash, q_facility_util, row=5, col=0, size_x=9, size_y=6)

    q_loan_status = create_question_with_display(
        host, session, db_id,
        "Loan Applications by Status",
        "SELECT status, COUNT(*) AS count FROM main_staging.stg_lending__loan_applications GROUP BY status ORDER BY count DESC",
        display="pie",
        collection_id=lending_coll,
    )
    add_card_to_dashboard(host, session, lending_dash, q_loan_status, row=5, col=9, size_x=9, size_y=6)

    q_repayment_schedule = create_question_with_display(
        host, session, db_id,
        "Upcoming Repayments",
        "SELECT installment_due_date, SUM(installment_amount) AS amount FROM main_intermediate.int_repayment_schedule WHERE installment_due_date >= CURRENT_DATE GROUP BY installment_due_date ORDER BY installment_due_date LIMIT 30",
        display="bar",
        collection_id=lending_coll,
        viz_settings={"graph.dimensions": ["installment_due_date"], "graph.metrics": ["amount"]},
    )
    add_card_to_dashboard(host, session, lending_dash, q_repayment_schedule, row=11, col=0, size_x=18, size_y=6)

    # ------------------------------------------------------------------
    # Payments Dashboard
    # ------------------------------------------------------------------
    print("==> Creating Payments dashboard...")
    payments_dash = create_dashboard(host, session, "Payments Overview", payments_coll)

    add_text_to_dashboard(host, session, payments_dash, "# Payments Overview", row=0, col=0, size_y=1)

    q_total_mrr = create_question(
        host, session, db_id,
        "Total MRR",
        "SELECT SUM(mrr_amount) AS total_mrr FROM main_marts.dim_customers",
        payments_coll,
    )
    add_card_to_dashboard(host, session, payments_dash, q_total_mrr, row=1, col=0, size_x=6, size_y=4)

    q_total_invoiced = create_question(
        host, session, db_id,
        "Total Invoiced Amount",
        "SELECT SUM(amount) AS total_invoiced FROM main_staging.stg_payments__invoices",
        payments_coll,
    )
    add_card_to_dashboard(host, session, payments_dash, q_total_invoiced, row=1, col=6, size_x=6, size_y=4)

    q_invoice_status = create_question_with_display(
        host, session, db_id,
        "Invoices by Status",
        "SELECT status, COUNT(*) AS count, SUM(amount) AS total FROM main_staging.stg_payments__invoices GROUP BY status ORDER BY total DESC",
        display="bar",
        collection_id=payments_coll,
        viz_settings={"graph.dimensions": ["status"], "graph.metrics": ["total"]},
    )
    add_card_to_dashboard(host, session, payments_dash, q_invoice_status, row=5, col=0, size_x=9, size_y=6)

    q_sub_status = create_question_with_display(
        host, session, db_id,
        "Subscriptions by Status",
        "SELECT status, COUNT(*) AS count FROM main_staging.stg_payments__subscriptions GROUP BY status ORDER BY count DESC",
        display="pie",
        collection_id=payments_coll,
    )
    add_card_to_dashboard(host, session, payments_dash, q_sub_status, row=5, col=9, size_x=9, size_y=6)

    # ------------------------------------------------------------------
    # Banking & FX Dashboard
    # ------------------------------------------------------------------
    print("==> Creating Banking & FX dashboard...")
    banking_dash = create_dashboard(host, session, "Banking & FX", banking_coll)

    add_text_to_dashboard(host, session, banking_dash, "# Banking & FX", row=0, col=0, size_y=1)

    q_total_fx_volume = create_question(
        host, session, db_id,
        "Total FX Transaction Volume",
        "SELECT SUM(base_amount) AS total_volume FROM main_marts.fct_fx_transactions WHERE is_orphaned = FALSE",
        banking_coll,
    )
    add_card_to_dashboard(host, session, banking_dash, q_total_fx_volume, row=1, col=0, size_x=6, size_y=4)

    q_avg_bal = create_question(
        host, session, db_id,
        "Average Account Balance",
        "SELECT currency, AVG(balance) AS avg_balance FROM main_staging.stg_banking__account_balances GROUP BY currency ORDER BY avg_balance DESC",
        banking_coll,
    )
    add_card_to_dashboard(host, session, banking_dash, q_avg_bal, row=1, col=6, size_x=6, size_y=4)

    q_fx_by_currency = create_question_with_display(
        host, session, db_id,
        "FX Transactions by Currency Pair",
        "SELECT base_currency, quote_currency, COUNT(*) AS tx_count, SUM(base_amount) AS total_volume FROM main_marts.fct_fx_transactions WHERE is_orphaned = FALSE GROUP BY base_currency, quote_currency ORDER BY tx_count DESC",
        display="table",
        collection_id=banking_coll,
    )
    add_card_to_dashboard(host, session, banking_dash, q_fx_by_currency, row=5, col=0, size_x=18, size_y=6)

    q_orphaned_fx = create_question(
        host, session, db_id,
        "Orphaned FX Transactions",
        "SELECT COUNT(*) AS orphaned_count FROM main_marts.fct_fx_transactions WHERE is_orphaned = TRUE",
        banking_coll,
    )
    add_card_to_dashboard(host, session, banking_dash, q_orphaned_fx, row=1, col=12, size_x=6, size_y=4)

    # ------------------------------------------------------------------
    # Executive Dashboard
    # ------------------------------------------------------------------
    print("==> Creating Executive dashboard...")
    exec_dash = create_dashboard(host, session, "Executive Summary", executive_coll)

    add_text_to_dashboard(host, session, exec_dash, "# Executive Summary", row=0, col=0, size_y=1)

    q_total_customers = create_question(
        host, session, db_id,
        "Total Customers",
        "SELECT COUNT(*) AS total_customers FROM main_marts.dim_customers",
        executive_coll,
    )
    add_card_to_dashboard(host, session, exec_dash, q_total_customers, row=1, col=0, size_x=4, size_y=3)

    q_lifetime_arr = create_question(
        host, session, db_id,
        "Lifetime ARR",
        "SELECT SUM(lifetime_arr) AS total_arr FROM main_marts.dim_customers",
        executive_coll,
    )
    add_card_to_dashboard(host, session, exec_dash, q_lifetime_arr, row=1, col=4, size_x=4, size_y=3)

    q_avg_utilization = create_question(
        host, session, db_id,
        "Average Facility Utilization",
        "SELECT AVG(utilization_pct) AS avg_util FROM main_marts.dim_credit_facilities WHERE status = 'active'",
        executive_coll,
    )
    add_card_to_dashboard(host, session, exec_dash, q_avg_utilization, row=1, col=8, size_x=4, size_y=3)

    q_orphan_count = create_question(
        host, session, db_id,
        "Data Quality: Orphaned Records",
        "SELECT 'drawdowns' AS entity, COUNT(*) AS orphans FROM main_marts.fct_drawdowns WHERE is_orphaned = TRUE UNION ALL SELECT 'repayments', COUNT(*) FROM main_marts.fct_repayments WHERE is_orphaned = TRUE UNION ALL SELECT 'fx_transactions', COUNT(*) FROM main_marts.fct_fx_transactions WHERE is_orphaned = TRUE",
        executive_coll,
    )
    add_card_to_dashboard(host, session, exec_dash, q_orphan_count, row=1, col=12, size_x=6, size_y=3)

    q_top_customers = create_question_with_display(
        host, session, db_id,
        "Top 10 Customers by ARR",
        "SELECT company_name, lifetime_arr, total_facility_limit, total_drawn_amount FROM main_marts.dim_customers ORDER BY lifetime_arr DESC NULLS LAST LIMIT 10",
        display="table",
        collection_id=executive_coll,
    )
    add_card_to_dashboard(host, session, exec_dash, q_top_customers, row=4, col=0, size_x=18, size_y=6)

    print()
    print("==> Dashboard provisioning complete!")
    print(f"    Lending Overview:  {host}/dashboard/{lending_dash}")
    print(f"    Payments Overview:  {host}/dashboard/{payments_dash}")
    print(f"    Banking & FX:      {host}/dashboard/{banking_dash}")
    print(f"    Executive Summary:  {host}/dashboard/{exec_dash}")


if __name__ == "__main__":
    main()