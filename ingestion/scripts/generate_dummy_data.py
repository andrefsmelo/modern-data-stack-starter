#!/usr/bin/env python3
"""
Generate synthetic dummy data for the data platform test suite.

Produces dirty, realistic Parquet files across 9 entities, partitioned by
day in Hive format (year=YYYY/month=MM/day=DD).  The data simulates a
European fintech platform serving ~120 SaaS companies.

Usage:
    python generate_dummy_data.py --output-dir ./data --seed 42 --start-date 2026-01-01 --days 30
"""

import argparse
import json
import os
import random
import uuid
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from faker import Faker

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MARKETS = [
    {"country": "GB", "currency": "GBP", "name": "United Kingdom"},
    {"country": "DE", "currency": "EUR", "name": "Germany"},
    {"country": "CH", "currency": "CHF", "name": "Switzerland"},
    {"country": "NL", "currency": "EUR", "name": "Netherlands"},
    {"country": "SE", "currency": "SEK", "name": "Sweden"},
    {"country": "NO", "currency": "NOK", "name": "Norway"},
    {"country": "FI", "currency": "EUR", "name": "Finland"},
    {"country": "DK", "currency": "DKK", "name": "Denmark"},
    {"country": "EE", "currency": "EUR", "name": "Estonia"},
    {"country": "ES", "currency": "EUR", "name": "Spain"},
    {"country": "BE", "currency": "EUR", "name": "Belgium"},
    {"country": "LT", "currency": "EUR", "name": "Lithuania"},
    {"country": "IE", "currency": "EUR", "name": "Ireland"},
    {"country": "AT", "currency": "EUR", "name": "Austria"},
    {"country": "IS", "currency": "ISK", "name": "Iceland"},
]

SEGMENTS = {
    "seed": {"share": 0.25, "arr_range": (200_000, 1_000_000), "facility_range": (50_000, 500_000), "drawdowns": (1, 3), "growth": (0.8, 1.5)},
    "growth": {"share": 0.55, "arr_range": (1_000_000, 20_000_000), "facility_range": (500_000, 5_000_000), "drawdowns": (3, 7), "growth": (1.5, 3.0)},
    "scale": {"share": 0.20, "arr_range": (20_000_000, 80_000_000), "facility_range": (5_000_000, 20_000_000), "drawdowns": (5, 12), "growth": (0.4, 1.0)},
}

VERTICALS = [
    "Revenue-management for independent hotels",
    "Whistleblowing, ethics hotlines, and HR tools",
    "Ad tracking, attribution, and optimization platform",
    "End-to-end retail management for furniture, bedding, and related retailers",
    "Project management and team collaboration",
    "Customer support automation",
    "Subscription billing and revenue recognition",
    "Identity and access management",
    "Cloud infrastructure monitoring",
    "E-commerce analytics and personalization",
    "Document automation and e-signatures",
    "Employee onboarding and training",
    "Data privacy and compliance automation",
    "API management and developer portals",
    "Inventory and supply chain forecasting",
]

PLAN_NAMES = ["Starter", "Professional", "Enterprise", "Growth", "Scale", "Custom"]

FX_PAIRS = [
    ("EUR", "GBP"), ("EUR", "USD"), ("EUR", "CHF"), ("EUR", "SEK"),
    ("EUR", "NOK"), ("EUR", "DKK"), ("GBP", "EUR"), ("GBP", "USD"),
    ("CHF", "EUR"), ("USD", "EUR"), ("SEK", "EUR"), ("NOK", "EUR"),
    ("ISK", "EUR"), ("EUR", "ISK"), ("EUR", "CAD"), ("CAD", "EUR"),
]

INVALID_CURRENCIES = ["EURO", "usd", "Pounds", "euro", "SEKr", ""]
DIRTY_DATE_FORMATS = ["%m/%d/%Y", "%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y"]

# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

class DirtyGenerator:
    """Wraps Faker and provides dirty-data injection helpers."""

    def __init__(self, seed: int):
        self.rng = random.Random(seed)
        self.np_rng = np.random.default_rng(seed)
        self.fake = Faker()
        self.fake.seed_instance(seed)

    # -- dirtiness helpers --------------------------------------------------

    def _chance(self, p: float) -> bool:
        return self.rng.random() < p

    def dirty_currency(self, clean_currency: str, dirty_prob: float = 0.08) -> str:
        if self._chance(dirty_prob):
            return self.rng.choice(INVALID_CURRENCIES)
        return clean_currency

    def dirty_date(self, dt: datetime, dirty_prob: float = 0.06) -> str:
        if self._chance(dirty_prob):
            fmt = self.rng.choice(DIRTY_DATE_FORMATS)
            return dt.strftime(fmt)
        if self._chance(0.03):
            # unix timestamp as string
            return str(int(dt.timestamp()))
        if self._chance(0.02):
            return dt.strftime("%m/%d/%Y")  # common US-style mistake
        return dt.isoformat()

    def dirty_amount_type(self, amount: float, dirty_prob: float = 0.07):
        """Return amount as string, int (cents), or float depending on randomness."""
        if self._chance(dirty_prob):
            return str(int(amount * 100))  # cents as string
        if self._chance(dirty_prob):
            return str(amount)  # string representation
        if self._chance(dirty_prob):
            return int(amount * 100)  # cents as int
        return round(amount, 2)

    def dirty_rate(self, rate: float, inverse_prob: float = 0.05) -> float:
        if self._chance(inverse_prob):
            return round(1.0 / rate, 6)
        return round(rate, 6)

    def dirty_empty_string(self, value: Optional[str], prob: float = 0.05) -> Optional[str]:
        if value is None:
            return None
        if self._chance(prob):
            return ""
        return value

    def dirty_negative(self, amount: float, prob: float = 0.03) -> float:
        if self._chance(prob):
            return -abs(amount)
        return amount

    def dirty_null_pk(self, pk: str, prob: float = 0.02) -> Optional[str]:
        if self._chance(prob):
            return None
        return pk

    def maybe_duplicate(self, items: List[Dict], prob: float = 0.04) -> List[Dict]:
        if not items:
            return items
        if self._chance(prob):
            dup = dict(self.rng.choice(items))
            # Slightly offset the timestamp so dedup logic picks "latest"
            dup["_ingested_at"] = dup["_ingested_at"] + timedelta(seconds=1)
            items.append(dup)
        return items

    def dirty_column_name(self, name: str, variant_prob: float = 0.10) -> str:
        """Occasionally swap a canonical snake_case name for a dirty variant."""
        if not self._chance(variant_prob):
            return name
        variants = {
            "customer_id": ["customerId", "Customer_ID", "customer_id"],
            "subscription_id": ["subscriptionId", "SubscriptionID", "subscription_id"],
            "invoice_id": ["invoiceId", "Invoice_ID", "invoice_id"],
            "application_id": ["applicationId", "ApplicationID", "application_id"],
            "facility_id": ["facilityId", "Facility_ID", "facility_id"],
            "drawdown_id": ["drawdownId", "Drawdown_ID", "drawdown_id"],
            "repayment_id": ["repaymentId", "Repayment_ID", "repayment_id"],
            "transaction_id": ["transactionId", "Transaction_ID", "transaction_id"],
            "snapshot_id": ["snapshotId", "Snapshot_ID", "snapshot_id"],
            "metric_id": ["metricId", "Metric_ID", "metric_id"],
            "mrr_amount": ["mrrAmount", "MRR_Amount", "mrr_amount"],
            "facility_limit": ["facilityLimit", "Facility_Limit", "facility_limit"],
            "drawdown_amount": ["drawdownAmt", "Drawdown_Amount", "drawdown_amount"],
            "repayment_amount": ["repaymentAmt", "Repayment_Amount", "repayment_amount"],
            "created_at": ["createdAt", "Created_At", "created_at"],
            "company_name": ["companyName", "Company_Name", "company_name"],
            "country_code": ["countryCode", "Country_Code", "country_code"],
            "arr_reported": ["arrReported", "ARR_Reported", "arr_reported"],
        }
        if name in variants:
            return self.rng.choice(variants[name])
        return name

    def dirty_schema_drift_drop(self, df: pd.DataFrame, col: str, drop_prob: float = 0.05) -> pd.DataFrame:
        if self._chance(drop_prob) and col in df.columns:
            return df.drop(columns=[col])
        return df

    def dirty_schema_drift_add(self, df: pd.DataFrame, col: str, values: Any, add_prob: float = 0.05) -> pd.DataFrame:
        if self._chance(add_prob) and col not in df.columns:
            df[col] = values
        return df

    # -- post-processing helpers --------------------------------------------

    def dirty_amount_column(self, df: pd.DataFrame, col: str, dirty_prob: float = 0.15) -> pd.DataFrame:
        """
        Apply a single dirty type mode to an entire numeric column.
        Per the spec, mixed types appear *across batches*, not within one file.
        """
        if col not in df.columns:
            return df
        if not self._chance(dirty_prob):
            return df
        mode = self.rng.choice(["string_cents", "string_major", "int_cents"])
        if mode == "string_cents":
            df[col] = df[col].apply(lambda x: str(int(float(x) * 100)) if pd.notna(x) else x)
        elif mode == "string_major":
            df[col] = df[col].apply(lambda x: str(round(float(x), 2)) if pd.notna(x) else x)
        elif mode == "int_cents":
            df[col] = df[col].apply(lambda x: int(float(x) * 100) if pd.notna(x) else x)
        return df

    # -- random value helpers -----------------------------------------------

    def uuid(self) -> str:
        return str(uuid.uuid4())

    def pick_segment(self) -> str:
        weights = [SEGMENTS[s]["share"] for s in SEGMENTS]
        return self.np_rng.choice(list(SEGMENTS.keys()), p=weights)

    def arr_for_segment(self, segment: str) -> float:
        low, high = SEGMENTS[segment]["arr_range"]
        return float(self.np_rng.integers(low, high + 1))

    def facility_for_segment(self, segment: str, arr: float) -> float:
        low, high = SEGMENTS[segment]["facility_range"]
        # Facility should be <= 70% of ARR (platform max)
        max_by_arr = arr * 0.70
        cap = min(high, max_by_arr)
        return float(self.np_rng.integers(low, int(cap) + 1))

    def growth_for_segment(self, segment: str) -> float:
        low, high = SEGMENTS[segment]["growth"]
        return round(self.np_rng.uniform(low, high), 2)

    def drawdown_count_for_segment(self, segment: str) -> int:
        low, high = SEGMENTS[segment]["drawdowns"]
        return int(self.np_rng.integers(low, high + 1))

    def fx_rate(self, base: str, quote: str) -> float:
        # Rough approximations for test data
        rates = {
            ("EUR", "GBP"): 0.85, ("EUR", "USD"): 1.08, ("EUR", "CHF"): 0.94,
            ("EUR", "SEK"): 11.5, ("EUR", "NOK"): 11.8, ("EUR", "DKK"): 7.45,
            ("GBP", "EUR"): 1.18, ("GBP", "USD"): 1.27, ("CHF", "EUR"): 1.06,
            ("USD", "EUR"): 0.93, ("SEK", "EUR"): 0.087, ("NOK", "EUR"): 0.085,
            ("ISK", "EUR"): 0.0067, ("EUR", "ISK"): 149.0, ("EUR", "CAD"): 1.47,
            ("CAD", "EUR"): 0.68,
        }
        key = (base, quote)
        base_rate = rates.get(key, 1.0)
        noise = self.np_rng.normal(0, 0.02)
        return max(0.001, round(base_rate + noise, 6))


# ---------------------------------------------------------------------------
# Core generation
# ---------------------------------------------------------------------------

def generate_customers(dg: DirtyGenerator, n: int = 120) -> List[Dict]:
    """Generate the customer master list with segment assignments."""
    customers = []
    per_market = max(2, n // len(MARKETS))
    max_per_market = int(n * 0.20)

    market_counts = {m["country"]: 0 for m in MARKETS}
    assigned = 0

    # Ensure minimum 2 per market
    for m in MARKETS:
        for _ in range(2):
            if assigned >= n:
                break
            customers.append(_make_customer(dg, m))
            market_counts[m["country"]] += 1
            assigned += 1

    # Fill remainder respecting max 20%
    while assigned < n:
        m = dg.rng.choice(MARKETS)
        if market_counts[m["country"]] >= max_per_market:
            continue
        customers.append(_make_customer(dg, m))
        market_counts[m["country"]] += 1
        assigned += 1

    dg.rng.shuffle(customers)
    return customers


def _make_customer(dg: DirtyGenerator, market: Dict) -> Dict:
    segment = dg.pick_segment()
    arr = dg.arr_for_segment(segment)
    facility_limit = dg.facility_for_segment(segment, arr)
    growth = dg.growth_for_segment(segment)
    drawdowns = dg.drawdown_count_for_segment(segment)
    vertical = dg.rng.choice(VERTICALS)

    return {
        "customer_id": dg.uuid(),
        "company_name": dg.fake.company(),
        "country_code": market["country"],
        "currency": market["currency"],
        "segment": segment,
        "target_arr": arr,
        "target_facility_limit": facility_limit,
        "arr_growth": growth,
        "target_drawdowns": drawdowns,
        "vertical": vertical,
        "headcount_at_application": int(dg.np_rng.integers(5, 200)),
        "valuation_at_application": int(dg.np_rng.integers(500_000, 50_000_000)),
        "arr_at_application": int(arr / (1 + growth)),  # backward-computed baseline
    }


def generate_subscriptions(dg: DirtyGenerator, customers: List[Dict], days: int, start: datetime) -> pd.DataFrame:
    rows = []
    for cust in customers:
        n_subs = int(dg.np_rng.integers(15, 45))  # ~30 per customer on average
        mrr_per_sub = cust["target_arr"] / 12 / n_subs
        for i in range(n_subs):
            created = start - timedelta(days=int(dg.np_rng.integers(1, 365)))
            period_start = start + timedelta(days=int(dg.np_rng.integers(0, days)))
            period_end = period_start + timedelta(days=30)
            status = "active"
            if dg._chance(0.05):
                status = "cancelled"
            elif dg._chance(0.03):
                status = "paused"

            rows.append({
                "subscription_id": dg.uuid(),
                "customer_id": cust["customer_id"],
                "plan_id": f"plan_{dg.rng.randint(1, 20)}",
                "plan_name": dg.rng.choice(PLAN_NAMES),
                "mrr_amount": round(mrr_per_sub * dg.np_rng.uniform(0.5, 1.5), 2),
                "currency": dg.dirty_currency(cust["currency"]),
                "status": status,
                "billing_period_start": period_start,
                "billing_period_end": period_end,
                "quantity": int(dg.np_rng.integers(1, 50)),
                "created_at": created,
                "_ingested_at": start + timedelta(days=int(dg.np_rng.integers(0, days))),
                "_schema_version": 1,
            })
    return pd.DataFrame(rows)


def generate_invoices(dg: DirtyGenerator, customers: List[Dict], days: int, start: datetime) -> pd.DataFrame:
    rows = []
    for cust in customers:
        n_inv = int(dg.np_rng.integers(30, 90))  # ~60 per customer on average
        amount_per_inv = cust["target_arr"] / 12 / n_inv
        for i in range(n_inv):
            inv_date = start + timedelta(days=int(dg.np_rng.integers(0, days)))
            due = inv_date + timedelta(days=14)
            paid = inv_date + timedelta(days=int(dg.np_rng.integers(1, 20))) if dg._chance(0.85) else None
            status = "paid" if paid else dg.rng.choice(["open", "uncollectible"])
            line_items = json.dumps([{
                "description": dg.fake.bs(),
                "amount": round(amount_per_inv * dg.np_rng.uniform(0.8, 1.2), 2),
                "currency": cust["currency"],
            }])
            rows.append({
                "invoice_id": dg.uuid(),
                "customer_id": cust["customer_id"],
                "subscription_id": dg.uuid() if dg._chance(0.8) else None,
                "amount": round(amount_per_inv * dg.np_rng.uniform(0.8, 1.2), 2),
                "currency": dg.dirty_currency(cust["currency"]),
                "invoice_date": inv_date,
                "due_date": due,
                "paid_at": paid,
                "status": status,
                "line_items_json": line_items,
                "created_at": inv_date,
                "_ingested_at": start + timedelta(days=int(dg.np_rng.integers(0, days))),
                "_schema_version": 1,
            })
    return pd.DataFrame(rows)


def generate_loan_applications(dg: DirtyGenerator, customers: List[Dict], days: int, start: datetime) -> pd.DataFrame:
    rows = []
    for cust in customers:
        # Approved application
        app_date = start - timedelta(days=int(dg.np_rng.integers(30, 365)))
        rows.append({
            "application_id": dg.uuid(),
            "customer_id": cust["customer_id"],
            "company_name": cust["company_name"],
            "company_registration_number": dg.dirty_empty_string(dg.fake.bothify(text="########")),
            "country_code": dg.dirty_empty_string(cust["country_code"]),
            "industry": "SaaS",
            "requested_amount": round(cust["target_facility_limit"], 2),
            "currency": dg.dirty_currency(cust["currency"]),
            "application_date": app_date,
            "status": "approved",
            "credit_score": int(dg.np_rng.integers(300, 850)) if dg._chance(0.98) else dg.rng.choice([999, -50, 0, 1000]),
            "risk_rating": dg.rng.choice(["low", "medium", "high"]),
            "headcount_at_application": cust["headcount_at_application"],
            "valuation_at_application": cust["valuation_at_application"],
            "arr_at_application": cust["arr_at_application"],
            "created_at": app_date,
            "_ingested_at": start + timedelta(days=int(dg.np_rng.integers(0, days))),
            "_schema_version": 1,
        })

    # Add some rejected/pending applications (not linked to funded customers)
    n_extra = int(len(customers) * 0.25)
    for _ in range(n_extra):
        m = dg.rng.choice(MARKETS)
        app_date = start - timedelta(days=int(dg.np_rng.integers(30, 180)))
        rows.append({
            "application_id": dg.uuid(),
            "customer_id": dg.uuid(),  # orphaned / not in customer set
            "company_name": dg.fake.company(),
            "company_registration_number": dg.dirty_empty_string(dg.fake.bothify(text="########")),
            "country_code": m["country"],
            "industry": "SaaS",
            "requested_amount": int(dg.np_rng.integers(50_000, 2_000_000)),
            "currency": m["currency"],
            "application_date": app_date,
            "status": dg.rng.choice(["rejected", "pending", "cancelled"]),
            "credit_score": int(dg.np_rng.integers(300, 850)),
            "risk_rating": dg.rng.choice(["low", "medium", "high", "N/A"]),
            "headcount_at_application": int(dg.np_rng.integers(5, 100)),
            "valuation_at_application": int(dg.np_rng.integers(500_000, 10_000_000)),
            "arr_at_application": int(dg.np_rng.integers(200_000, 5_000_000)),
            "created_at": app_date,
            "_ingested_at": start + timedelta(days=int(dg.np_rng.integers(0, days))),
            "_schema_version": 1,
        })
    return pd.DataFrame(rows)


def generate_credit_facilities(dg: DirtyGenerator, customers: List[Dict], days: int, start: datetime) -> pd.DataFrame:
    rows = []
    for cust in customers:
        n_facilities = dg.rng.choices([1, 2, 3], weights=[0.75, 0.20, 0.05])[0]
        for f_idx in range(n_facilities):
            limit = cust["target_facility_limit"] * (0.6 if f_idx > 0 else 1.0)
            approval = start - timedelta(days=int(dg.np_rng.integers(30, 730)))
            maturity = approval + timedelta(days=365 * 2)
            status = "active" if f_idx == n_facilities - 1 else "closed"
            schedule = [
                {
                    "due_date": (approval + timedelta(days=30 * (i + 1))).strftime("%Y-%m-%d"),
                    "amount": round(limit * 0.05, 2),
                }
                for i in range(12)
            ]
            rows.append({
                "facility_id": dg.uuid(),
                "application_id": None,  # will link in clean pipeline; some orphans
                "customer_id": cust["customer_id"],
                "facility_limit": dg.dirty_negative(round(limit, 2), prob=0.01),
                "currency": dg.dirty_currency(cust["currency"]),
                "approval_date": approval,
                "maturity_date": maturity,
                "status": status,
                "interest_rate": round(dg.np_rng.uniform(0.08, 0.18), 4),
                "repayment_schedule_json": json.dumps(schedule),
                "created_at": approval,
                "_ingested_at": start + timedelta(days=int(dg.np_rng.integers(0, days))),
                "_schema_version": 1,
            })
    return pd.DataFrame(rows)


def generate_drawdowns(dg: DirtyGenerator, customers: List[Dict], facilities: pd.DataFrame, days: int, start: datetime) -> pd.DataFrame:
    rows = []
    facs = facilities.to_dict("records")
    for cust in customers:
        cust_facs = [f for f in facs if f["customer_id"] == cust["customer_id"]]
        n_drawdowns = cust["target_drawdowns"]
        for i in range(n_drawdowns):
            fac = dg.rng.choice(cust_facs) if cust_facs else None
            # Occasionally create orphan drawdowns even when facilities exist
            if dg._chance(0.05):
                fac = None
            amt = cust["target_facility_limit"] * dg.np_rng.uniform(0.1, 0.4)
            dd_date = start + timedelta(days=int(dg.np_rng.integers(0, max(1, days - 1))))
            rows.append({
                "drawdown_id": dg.dirty_null_pk(dg.uuid(), prob=0.02),
                "facility_id": fac["facility_id"] if fac else dg.uuid(),  # orphan if no fac
                "customer_id": cust["customer_id"],
                "amount": dg.dirty_negative(round(amt, 2)),
                "currency": dg.dirty_currency(cust["currency"]),
                "drawdown_date": dd_date,
                "purpose": dg.rng.choice(["working_capital", "expansion", "marketing", "hiring", None]),
                "status": dg.rng.choice(["completed", "completed", "completed", "pending"]),
                "created_at": dd_date,
                "_ingested_at": start + timedelta(days=int(dg.np_rng.integers(0, days))),
                "_schema_version": 1,
            })
    dg.maybe_duplicate(rows, prob=0.04)
    return pd.DataFrame(rows)


def generate_repayments(dg: DirtyGenerator, drawdowns: pd.DataFrame, days: int, start: datetime) -> pd.DataFrame:
    rows = []
    for dd in drawdowns.to_dict("records"):
        if dd.get("status") != "completed":
            continue
        n_repayments = int(dg.np_rng.integers(4, 8))
        base_due = dd["drawdown_date"] + timedelta(days=30)
        for i in range(n_repayments):
            due = base_due + timedelta(days=30 * i)
            amount = float(dd["amount"]) if isinstance(dd["amount"], (int, float)) else float(dd["amount"])
            scheduled = amount / n_repayments * dg.np_rng.uniform(0.9, 1.1)
            actual = scheduled if dg._chance(0.85) else None
            actual_date = due + timedelta(days=int(dg.np_rng.integers(-5, 10))) if actual else None
            rows.append({
                "repayment_id": dg.uuid(),
                "drawdown_id": dd["drawdown_id"],
                "facility_id": dd["facility_id"],
                "customer_id": dd["customer_id"],
                "scheduled_amount": round(scheduled, 2),
                "actual_amount": round(actual, 2) if actual else None,
                "currency": dg.dirty_currency(dd["currency"]),
                "due_date": due,
                "actual_date": actual_date,
                "status": "paid" if actual else dg.rng.choice(["scheduled", "overdue"]),
                "created_at": due,
                "_ingested_at": start + timedelta(days=int(dg.np_rng.integers(0, days))),
                "_schema_version": 1,
            })
    # Add orphaned repayments (~2% extra rows with random drawdown_id)
    n_orphan = max(1, int(len(rows) * 0.02))
    for _ in range(n_orphan):
        due = start + timedelta(days=int(dg.np_rng.integers(0, days)))
        rows.append({
            "repayment_id": dg.uuid(),
            "drawdown_id": dg.uuid(),  # orphaned
            "facility_id": dg.uuid(),
            "customer_id": dg.uuid(),
            "scheduled_amount": round(dg.np_rng.integers(1_000, 50_000), 2),
            "actual_amount": None,
            "currency": dg.dirty_currency(dg.rng.choice([m["currency"] for m in MARKETS])),
            "due_date": due,
            "actual_date": None,
            "status": "scheduled",
            "created_at": due,
            "_ingested_at": start + timedelta(days=int(dg.np_rng.integers(0, days))),
            "_schema_version": 1,
        })
    return pd.DataFrame(rows)


def generate_fx_transactions(dg: DirtyGenerator, customers: List[Dict], days: int, start: datetime) -> pd.DataFrame:
    rows = []
    for cust in customers:
        n_fx = dg.np_rng.integers(8, 25)
        for _ in range(n_fx):
            base, quote = dg.rng.choice(FX_PAIRS)
            base_amt = dg.np_rng.integers(1_000, 500_000)
            rate = dg.fx_rate(base, quote)
            rate = dg.dirty_rate(rate)
            tx_date = start + timedelta(days=int(dg.np_rng.integers(0, days)))
            rows.append({
                "transaction_id": dg.uuid(),
                "customer_id": cust["customer_id"],
                "base_currency": base,
                "quote_currency": quote,
                "base_amount": int(base_amt),
                "quote_amount": round(base_amt * rate, 2) if dg._chance(0.7) else None,
                "rate": rate,
                "rate_type": dg.rng.choice(["spot", "forward"]) if dg._chance(0.9) else None,
                "transaction_date": tx_date,
                "counterparty_bank_bic": dg.fake.bothify(text="????GB2L") if dg._chance(0.8) else None,
                "created_at": tx_date,
                "_ingested_at": start + timedelta(days=int(dg.np_rng.integers(0, days))),
                "_schema_version": 1,
            })
    return pd.DataFrame(rows)


def generate_account_balances(dg: DirtyGenerator, customers: List[Dict], days: int, start: datetime) -> pd.DataFrame:
    rows = []
    for cust in customers:
        for d in range(days):
            snap_date = start + timedelta(days=d)
            rows.append({
                "snapshot_id": dg.uuid(),
                "customer_id": cust["customer_id"],
                "account_id": f"acct_{cust['customer_id'][:8]}_{dg.rng.randint(1,3)}",
                "currency": dg.dirty_currency(cust["currency"]),
                "balance": int(dg.np_rng.integers(10_000, 2_000_000)),
                "snapshot_date": snap_date,
                "account_type": dg.rng.choice(["operating", "reserve", "fx"]),
                "created_at": snap_date,
                "_ingested_at": start + timedelta(days=int(dg.np_rng.integers(0, days))),
                "_schema_version": 1,
            })
    # Add orphaned balances (~2% extra rows with random customer_id)
    n_orphan = max(1, int(len(rows) * 0.02))
    for _ in range(n_orphan):
        snap_date = start + timedelta(days=int(dg.np_rng.integers(0, days)))
        rows.append({
            "snapshot_id": dg.uuid(),
            "customer_id": dg.uuid(),  # orphaned
            "account_id": f"acct_orphan_{dg.rng.randint(1, 999)}",
            "currency": dg.dirty_currency(dg.rng.choice([m["currency"] for m in MARKETS])),
            "balance": int(dg.np_rng.integers(10_000, 2_000_000)),
            "snapshot_date": snap_date,
            "account_type": dg.rng.choice(["operating", "reserve", "fx"]),
            "created_at": snap_date,
            "_ingested_at": start + timedelta(days=int(dg.np_rng.integers(0, days))),
            "_schema_version": 1,
        })
    return pd.DataFrame(rows)


def generate_company_metrics(dg: DirtyGenerator, customers: List[Dict], days: int, start: datetime) -> pd.DataFrame:
    rows = []
    for cust in customers:
        n_metrics = dg.np_rng.integers(2, 5)
        for i in range(n_metrics):
            metric_date = start + timedelta(days=int(dg.np_rng.integers(0, max(1, days - 1))))
            headcount = int(cust["headcount_at_application"] * (1 + dg.np_rng.uniform(0, cust["arr_growth"])))
            valuation = int(cust["valuation_at_application"] * (1 + dg.np_rng.uniform(0, cust["arr_growth"])))
            # Intentionally seed arr_reported to differ from computed ARR for some customers
            arr_variance = dg.np_rng.uniform(-0.15, 0.15) if dg._chance(0.30) else 0.0
            arr_reported = int(cust["target_arr"] * (1 + arr_variance))
            rows.append({
                "metric_id": dg.uuid(),
                "customer_id": cust["customer_id"],
                "metric_date": metric_date,
                "headcount": headcount,
                "valuation": valuation,
                "arr_reported": arr_reported,
                "created_at": metric_date,
                "_ingested_at": start + timedelta(days=int(dg.np_rng.integers(0, days))),
                "_schema_version": 1,
            })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Dirty transformations on DataFrames
# ---------------------------------------------------------------------------

def apply_date_dirtiness(dg: DirtyGenerator, df: pd.DataFrame, cols: List[str]) -> pd.DataFrame:
    for col in cols:
        if col not in df.columns:
            continue
        df[col] = df[col].apply(lambda x: dg.dirty_date(x) if pd.notna(x) else x)
    return df


def apply_column_name_dirtiness(dg: DirtyGenerator, df: pd.DataFrame) -> pd.DataFrame:
    """Rename a subset of columns to dirty variants."""
    rename_map = {}
    for col in df.columns:
        new_col = dg.dirty_column_name(col)
        if new_col != col:
            rename_map[col] = new_col
    if rename_map:
        df = df.rename(columns=rename_map)
    return df


def apply_schema_drift(dg: DirtyGenerator, df: pd.DataFrame, entity: str) -> pd.DataFrame:
    if entity == "credit_facilities":
        df = dg.dirty_schema_drift_add(df, "collateral_required", False, add_prob=0.10)
    if entity == "fx_transactions":
        df = dg.dirty_schema_drift_drop(df, "counterparty_bank_bic", drop_prob=0.08)
    if entity == "loan_applications":
        df = dg.dirty_schema_drift_add(df, "referral_source", dg.fake.word(), add_prob=0.08)
    return df


def apply_stale_partitions(dg: DirtyGenerator, df: pd.DataFrame, stale_prob: float = 0.05, stale_days: int = 45) -> pd.DataFrame:
    """Backdate _ingested_at for a random subset of rows to create stale partitions."""
    if df.empty or "_ingested_at" not in df.columns:
        return df
    mask = dg.np_rng.random(len(df)) < stale_prob
    if mask.any():
        # Subtract stale_days + random jitter from _ingested_at
        jitter = dg.np_rng.integers(0, 15, size=mask.sum())
        df.loc[mask, "_ingested_at"] = pd.to_datetime(df.loc[mask, "_ingested_at"]) - pd.to_timedelta(stale_days + jitter, unit="D")
    return df


# ---------------------------------------------------------------------------
# Writers
# ---------------------------------------------------------------------------

def write_partitioned(df: pd.DataFrame, entity: str, output_dir: str) -> None:
    if df.empty:
        return
    df["year"] = pd.to_datetime(df["_ingested_at"]).dt.year
    df["month"] = pd.to_datetime(df["_ingested_at"]).dt.month
    df["day"] = pd.to_datetime(df["_ingested_at"]).dt.day

    for (year, month, day), group in df.groupby(["year", "month", "day"]):
        path = os.path.join(output_dir, entity, f"year={year}", f"month={month:02d}", f"day={day:02d}")
        os.makedirs(path, exist_ok=True)
        file_name = entity.replace("/", "_") + f"_{year}{month:02d}{day:02d}.parquet"
        out_file = os.path.join(path, file_name)

        group = group.drop(columns=["year", "month", "day"])
        table = pa.Table.from_pandas(group, preserve_index=False)
        pq.write_table(table, out_file, compression="snappy")


def main():
    parser = argparse.ArgumentParser(description="Generate synthetic dummy data for platform testing")
    parser.add_argument("--output-dir", default="./data", help="Base output directory")
    parser.add_argument("--seed", type=int, default=42, help="Random seed for reproducibility")
    parser.add_argument("--start-date", default="2026-01-01", help="Start date (YYYY-MM-DD)")
    parser.add_argument("--days", type=int, default=30, help="Number of days to generate")
    parser.add_argument("--n-customers", type=int, default=120, help="Number of customers")
    args = parser.parse_args()

    start = datetime.strptime(args.start_date, "%Y-%m-%d")
    dg = DirtyGenerator(seed=args.seed)

    print("Generating customers...")
    customers = generate_customers(dg, n=args.n_customers)

    print("Generating subscriptions...")
    subs = generate_subscriptions(dg, customers, args.days, start)

    print("Generating invoices...")
    invs = generate_invoices(dg, customers, args.days, start)

    print("Generating loan applications...")
    apps = generate_loan_applications(dg, customers, args.days, start)

    print("Generating credit facilities...")
    facs = generate_credit_facilities(dg, customers, args.days, start)

    print("Generating drawdowns...")
    dds = generate_drawdowns(dg, customers, facs, args.days, start)

    print("Generating repayments...")
    reps = generate_repayments(dg, dds, args.days, start)

    print("Generating FX transactions...")
    fxs = generate_fx_transactions(dg, customers, args.days, start)

    print("Generating account balances...")
    bals = generate_account_balances(dg, customers, args.days, start)

    print("Generating company metrics...")
    metrics = generate_company_metrics(dg, customers, args.days, start)

    # Apply dirty transformations after all dependent entities are generated
    print("Applying dirty transformations...")
    subs = apply_date_dirtiness(dg, subs, ["billing_period_start", "billing_period_end", "created_at"])
    subs = apply_column_name_dirtiness(dg, subs)

    invs = apply_date_dirtiness(dg, invs, ["invoice_date", "due_date", "paid_at", "created_at"])
    invs = apply_column_name_dirtiness(dg, invs)

    apps = apply_date_dirtiness(dg, apps, ["application_date", "created_at"])
    apps = apply_column_name_dirtiness(dg, apps)
    apps = apply_schema_drift(dg, apps, "loan_applications")
    apps = dg.dirty_amount_column(apps, "requested_amount")

    facs = apply_date_dirtiness(dg, facs, ["approval_date", "maturity_date", "created_at"])
    facs = apply_column_name_dirtiness(dg, facs)
    facs = apply_schema_drift(dg, facs, "credit_facilities")
    facs = dg.dirty_amount_column(facs, "facility_limit")

    dds = apply_date_dirtiness(dg, dds, ["drawdown_date", "created_at"])
    dds = apply_column_name_dirtiness(dg, dds)
    dds = dg.dirty_amount_column(dds, "amount")

    reps = apply_date_dirtiness(dg, reps, ["due_date", "actual_date", "created_at"])
    reps = apply_column_name_dirtiness(dg, reps)
    reps = dg.dirty_amount_column(reps, "scheduled_amount")
    reps = dg.dirty_amount_column(reps, "actual_amount")

    fxs = apply_date_dirtiness(dg, fxs, ["transaction_date", "created_at"])
    fxs = apply_column_name_dirtiness(dg, fxs)
    fxs = apply_schema_drift(dg, fxs, "fx_transactions")
    fxs = dg.dirty_amount_column(fxs, "base_amount")
    fxs = dg.dirty_amount_column(fxs, "quote_amount")

    bals = apply_date_dirtiness(dg, bals, ["snapshot_date", "created_at"])
    bals = apply_column_name_dirtiness(dg, bals)
    bals = dg.dirty_amount_column(bals, "balance")

    metrics = apply_date_dirtiness(dg, metrics, ["metric_date", "created_at"])
    metrics = apply_column_name_dirtiness(dg, metrics)
    metrics = dg.dirty_amount_column(metrics, "valuation")
    metrics = dg.dirty_amount_column(metrics, "arr_reported")

    # Create stale partitions (~5% of rows backdated 45+ days)
    print("Creating stale partitions...")
    subs = apply_stale_partitions(dg, subs)
    invs = apply_stale_partitions(dg, invs)
    apps = apply_stale_partitions(dg, apps)
    facs = apply_stale_partitions(dg, facs)
    dds = apply_stale_partitions(dg, dds)
    reps = apply_stale_partitions(dg, reps)
    fxs = apply_stale_partitions(dg, fxs)
    bals = apply_stale_partitions(dg, bals)
    metrics = apply_stale_partitions(dg, metrics)

    # Write everything
    print("Writing Parquet files...")
    write_partitioned(subs, "payments/subscriptions", args.output_dir)
    write_partitioned(invs, "payments/invoices", args.output_dir)
    write_partitioned(apps, "lending/loan_applications", args.output_dir)
    write_partitioned(facs, "lending/credit_facilities", args.output_dir)
    write_partitioned(dds, "lending/drawdowns", args.output_dir)
    write_partitioned(reps, "lending/repayments", args.output_dir)
    write_partitioned(fxs, "banking/fx_transactions", args.output_dir)
    write_partitioned(bals, "banking/account_balances", args.output_dir)
    write_partitioned(metrics, "crm/company_metrics", args.output_dir)

    # Summary
    print("\nDone. Generated:")
    print(f"  Customers:     {len(customers)}")
    print(f"  Subscriptions: {len(subs)}")
    print(f"  Invoices:      {len(invs)}")
    print(f"  Applications:  {len(apps)}")
    print(f"  Facilities:    {len(facs)}")
    print(f"  Drawdowns:     {len(dds)}")
    print(f"  Repayments:    {len(reps)}")
    print(f"  FX txs:        {len(fxs)}")
    print(f"  Balances:      {len(bals)}")
    print(f"  Metrics:       {len(metrics)}")
    print(f"\nOutput: {args.output_dir}")


if __name__ == "__main__":
    main()
