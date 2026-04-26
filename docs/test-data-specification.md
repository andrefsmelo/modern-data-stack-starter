# Dummy Data Specification

> Constraints for synthetic test data used to validate the entire data pipeline — from ingestion through transformation to consumption.

## Purpose

The dummy data simulates **real-world raw data** produced by a **European fintech platform that provides revenue-based financing, multi-currency accounts, and FX services to SaaS companies**. The raw data arrives in a **messy, non-standard format** from multiple upstream systems (payment processors, banking partners, internal CRM, and a proprietary lending engine). It is intentionally "dirty" so the project can exercise all transformation layers: cleansing in staging, business-rule enforcement in intermediate, and final modeling in marts.

After transformation, the data must conform to a clean, **consumption-ready schema** suitable for BI dashboards, credit-risk analysis, and regulatory reporting.

## Sources & Entities

Four logical source systems feed raw data into S3 under the standard path layout. The source names are anonymized but representative of a real fintech stack.

| Source System | Entity | S3 Raw Path | Business Meaning |
|---|---|---|---|
| `payments` | `subscriptions` | `s3://{bucket}/raw/payments/subscriptions/year={yyyy}/month={mm}/day={dd}/` | SaaS subscription records used to estimate ARR |
| `payments` | `invoices` | `s3://{bucket}/raw/payments/invoices/year={yyyy}/month={mm}/day={dd}/` | Billing events and cash-flow timestamps |
| `lending` | `loan_applications` | `s3://{bucket}/raw/lending/loan_applications/year={yyyy}/month={mm}/day={dd}/` | Funding requests with requested amount and status |
| `lending` | `credit_facilities` | `s3://{bucket}/raw/lending/credit_facilities/year={yyyy}/month={mm}/day={dd}/` | Approved credit lines, limits, and linked revenue metrics |
| `lending` | `drawdowns` | `s3://{bucket}/raw/lending/drawdowns/year={yyyy}/month={mm}/day={dd}/` | Capital withdrawals against an approved facility |
| `lending` | `repayments` | `s3://{bucket}/raw/lending/repayments/year={yyyy}/month={mm}/day={dd}/` | Scheduled and actual revenue-share repayments |
| `banking` | `fx_transactions` | `s3://{bucket}/raw/banking/fx_transactions/year={yyyy}/month={mm}/day={dd}/` | Currency conversions and cross-border payment events |
| `banking` | `account_balances` | `s3://{bucket}/raw/banking/account_balances/year={yyyy}/month={mm}/day={dd}/` | Daily snapshot of multi-currency account balances |
| `crm` | `company_metrics` | `s3://{bucket}/raw/crm/company_metrics/year={yyyy}/month={mm}/day={dd}/` | Monthly snapshots of headcount, valuation, and self-reported ARR |

*Note: Source names (`payments`, `lending`, `banking`, `crm`) are placeholders. In production these would map to actual integrations (e.g., Stripe, an internal loan engine, a banking-as-a-service provider, HubSpot / Salesforce).*

## Volume & Scale

The dummy data must reflect the following operational footprint. These numbers drive cardinality in foreign keys, the diversity of currency codes, and the realism of ARR/facility distributions.

| Metric | Target |
|---|---|
| Funded SaaS companies (customers) | ~120 |
| Loans / drawdowns deployed | ~400 |
| Active markets (countries) | 16 |
| Daily history (test scope) | ~30 days |

### Market Distribution

Customers and facilities must be distributed across the following **16 European markets**. Country codes and primary currencies must be respected in raw data so that FX and regulatory tests exercise realistic diversity.

| Market | ISO Country Code | Primary Currency |
|---|---|---|
| United Kingdom | `GB` | `GBP` |
| Germany | `DE` | `EUR` |
| Switzerland | `CH` | `CHF` |
| Netherlands | `NL` | `EUR` |
| Sweden | `SE` | `SEK` |
| Norway | `NO` | `NOK` |
| Finland | `FI` | `EUR` |
| Denmark | `DK` | `DKK` |
| Estonia | `EE` | `EUR` |
| Spain | `ES` | `EUR` |
| Belgium | `BE` | `EUR` |
| Lithuania | `LT` | `EUR` |
| Ireland | `IE` | `EUR` |
| Austria | `AT` | `EUR` |
| Iceland | `IS` | `ISK` |

**Distribution rules for the generator:**
- No single market should hold more than 20 % of customers.
- At least 2 customers must exist in each of the 16 markets.
- Currency codes in raw data must match the market’s primary currency above (dirty-data rules still apply — some files may contain invalid codes that the staging layer must cleanse).

## Entity Cardinality

The ~120 customers and ~400 drawdowns should produce approximately these row counts per entity over the 30-day test window:

| Entity | Approx. Rows | Notes |
|---|---|---|---|
| `customers` (from `loan_applications`) | ~120 | 1 row per funded company; some duplicates and NULL PKs for dirty-data tests |
| `subscriptions` | ~3,600 | ~30 per customer (monthly SaaS subscription events) |
| `invoices` | ~7,200 | ~60 per customer (bi-weekly billing cycles) |
| `loan_applications` | ~150 | ~120 approved + 30 pending or rejected |
| `credit_facilities` | ~150 | ~1.25 per funded customer on average; some customers have 2–3 sequential facilities (top-ups / renewals) |
| `company_metrics` | ~360 | ~3 snapshots per customer over the 30-day window (monthly cadence) |
| `drawdowns` | ~550 | ~4.5 per facility on average; distributed over 30 days |
| `repayments` | ~2,400 | ~6 scheduled repayments per drawdown (monthly revenue-share cadence) |
| `fx_transactions` | ~1,800 | ~15 per customer (cross-border payment and conversion events) |
| `account_balances` | ~3,600 | 1 daily snapshot per customer per day |

## Customer Segment & Revenue Distribution

The ~120 funded companies must span realistic SaaS verticals and growth stages. The generator should use the following segment buckets so that ARR, facility limits, and drawdown counts produce believable credit-utilization curves in BI dashboards.

| Segment | Share of Customers | ARR Range | Facility Limit Range | Avg. Drawdowns | Typical Growth |
|---|---|---|---|---|---|
| Seed / Early | ~25 % (30) | €200k – €1m | €50k – €500k | 1 – 2 | 80 % – 150 % |
| Growth / Mid-Market | ~55 % (66) | €1m – €20m | €500k – €5m | 3 – 6 | 150 % – 300 % |
| Scale | ~20 % (24) | €20m – €80m | €5m – €20m | 5 – 12 | 40 % – 100 % |

### Reference Profile — Growth / Mid-Market Segment

The following anonymized real-world profile guides the generator for the Growth / Mid-Market bucket. It ensures that synthetic metrics (ARR, facility size, utilization, drawdown cadence) are internally consistent.

| Attribute | Value |
|---|---|
| Vertical | SaaS — Revenue-management for independent hotels |
| Business model | B2B SaaS (subscription) |
| Current ARR | €14,000,000 |
| Max credit facility (single) | €2,000,000 |
| Total credit used (lifetime across facilities / top-ups) | €3,000,000 |
| Number of drawdowns (loans) | 11 |
| ARR growth (YoY) | 260 % |
| HQ market | `NL` / `EUR` |

**Generator rules derived from this profile:**
- Facility limit is generally **≤ 15 % – 20 % of current ARR** for the Growth segment (not the full 70 % headline; that is the platform maximum and applies only to the largest, lowest-risk accounts).
- Total credit used can exceed the max facility of a single facility because customers may receive sequential facilities, top-ups, or renewals as ARR grows.
- Number of drawdowns correlates with facility age: older or faster-growing customers have more drawdown events.
- Subscriptions and invoices must be consistent with the declared ARR (e.g., €14m ARR ≈ €1.17m MRR ≈ ~500 – 2,000 subscription events per month depending on average contract value).

### Reference Profile — Seed / Early Segment

The following anonymized real-world profile guides the generator for the Seed / Early bucket. It represents a younger, high-growth SaaS company that uses revenue-based financing to bridge to an equity round.

| Attribute | Value |
|---|---|
| Vertical | SaaS — Whistleblowing, ethics hotlines, and HR tools |
| Business model | B2B SaaS (subscription) |
| Current ARR | €1,000,000 |
| Credit facility (single) | €600,000 |
| Number of drawdowns (loans) | 2 |
| Valuation increase since first facility | 3× |
| ARR growth (since inception / funding) | 10× |
| HQ market | `IS` / `ISK` (converted to `EUR` for facility reporting) |

**Generator rules derived from this profile:**
- Facility size is **≤ 60 % of current ARR** for Seed / Early accounts (vs. ~15 % for Growth). These customers have less historical revenue data, so limits are tighter relative to ARR but still meaningful in absolute terms.
- Number of drawdowns is low (1–3) because the facility is young and the customer may raise equity before fully utilizing it.
- Valuation increase and ARR growth are tracked as **customer lifecycle metrics** in `dim_customers`, sourced from `crm.company_metrics` and compared against `loan_applications` baseline values.
- Subscriptions and invoices must be consistent with €1m ARR (≈ €83k MRR ≈ ~30 – 150 subscription events per month for mid-market B2B contract values).
- Currency conversion: raw subscription data may be in the local currency (`ISK`), while the facility is denominated in `EUR`. The FX layer must handle this cleanly.

### Reference Profile — Early Growth Segment

The following anonymized real-world profile guides the generator for the lower end of the Growth / Mid-Market bucket. It represents a high-growth SaaS company that used revenue-based financing to reach profitability while doubling both ARR and headcount.

| Attribute | Value |
|---|---|
| Vertical | SaaS — Ad tracking, attribution, and optimization platform |
| Business model | B2B SaaS (subscription) |
| ARR at facility start | €1,500,000 |
| Credit facility | €600,000 |
| Number of drawdowns (loans) | 3 |
| ARR growth (since facility start) | 100 % |
| Team growth (since facility start) | 100 % |
| HQ market | `LT` / `EUR` |

**Generator rules derived from this profile:**
- Facility size is **~40 % of ARR at inception** for Early Growth accounts that are still pre-profitability. This sits between the Seed/Early ratio (~60 %) and the mature Growth ratio (~15 %). The limit reflects higher risk than a €14m ARR account but also demonstrated traction.
- Low drawdown count (3) indicates a newer or more cautiously utilized facility. The customer used the capital selectively to fund growth rather than drawing the full limit.
- **Team growth** is a new lifecycle metric tracked in `dim_customers` (headcount at facility start vs. current). It validates the platform’s thesis that financing enables hiring and therefore faster revenue growth.
- Subscriptions and invoices must be consistent with €1.5m ARR at the start of the facility (≈ €125k MRR). Over the 30-day test window, the generator should model growth so that current ARR approaches €3m if the full historical period is simulated.

### Reference Profile — Multi-Market Growth Segment

The following anonymized real-world profile guides the generator for a customer that operates across multiple European and non-European markets. It represents a traditional-sector SaaS company with a long platform relationship and high facility utilization through sequential top-ups.

| Attribute | Value |
|---|---|
| Vertical | SaaS — End-to-end retail management for furniture, bedding, and related retailers |
| Business model | B2B SaaS (subscription) |
| Current ARR | €1,000,000 |
| Current credit facility | €500,000 |
| Total credit used (lifetime across facilities / top-ups) | €1,400,000 |
| Number of drawdowns (loans) | 13 |
| ARR growth (YoY) | 100 % |
| Active markets | `IE` / `EUR`, `GB` / `GBP`, `CA` / `CAD` |

**Generator rules derived from this profile:**
- **Total credit used > current facility limit** (€1.4m vs. €500k). This is a critical test case for the data model: `credit_facilities` must support **multiple sequential facilities** per customer, and `dim_customers` must aggregate `total_facility_limit` (sum of active facility limits) separately from `total_drawn_amount` (sum of all drawdowns across all historical facilities).
- High drawdown count (13) indicates a mature, multi-year relationship with the platform. The customer has drawn repeatedly, suggesting the facility was renewed or topped up as ARR grew.
- **Multi-market / multi-currency presence**: subscriptions and invoices may be denominated in `EUR` (Ireland), `GBP` (UK), and `CAD` (Canada). The FX layer must convert all amounts to a **reporting currency** (`EUR`) for facility-level aggregation, while preserving the original currency in `fct_fx_transactions` and `fct_drawdowns`.
- **Traditional-sector SaaS**: lower subscription event count per €1m ARR (≈ €83k MRR ≈ ~15 – 60 subscription events per month) because average contract values are higher for retail-management software than horizontal tools.
- The customer's ARR is €1m but total credit used is €1.4m — this validates that the platform **does not cap lifetime exposure at current ARR**. Instead, facility renewals are based on forward-looking ARR growth and repayment history.

### Important: Reference Metrics Are Computed, Not Stored

All metrics listed in the reference profiles above (ARR, total credit used, ARR growth, utilization, etc.) are **target outcomes** that the dbt pipeline must compute from base entities. They must **not** appear as pre-aggregated columns in raw Parquet files. The generator should produce granular transactional rows only; the transformation layer handles all roll-ups.

| Target Metric | Source Entities | Computation Method |
|---|---|---|
| Current ARR | `subscriptions` (preferred) or `invoices` | Sum of active subscription MRR × 12; or sum of paid recurring invoices in trailing 12 months |
| ARR growth | `subscriptions` + `invoices` | Month-over-month or year-over-year change in computed ARR |
| Total credit used | `drawdowns` | Sum of `amount` for all completed drawdowns per customer, across all historical facilities |
| Current facility limit | `credit_facilities` | Sum of `facility_limit` for all active facilities per customer |
| Utilization % | `credit_facilities` + `drawdowns` | `total_drawn_amount / total_facility_limit * 100` for active facilities |
| Team growth | `loan_applications` + `crm.company_metrics` | `(latest_headcount - headcount_at_application) / headcount_at_application * 100` |
| Valuation increase | `loan_applications` + `crm.company_metrics` | `latest_valuation / valuation_at_application` |
| Self-reported vs computed ARR variance | `crm.company_metrics` + `subscriptions` | `arr_reported` from CRM minus computed ARR from subscription data |

## Raw Entity Schemas

The following column specifications define what the generator must produce for each entity. All monetary amounts are in the entity's stated `currency` unless otherwise noted. Column names are shown in canonical `snake_case`; the generator may emit dirty variants per the rules below.

### `payments.subscriptions`

| Column | Type (Raw) | Nullable | Notes |
|---|---|---|---|
| `subscription_id` | `STRING` | No | Primary key |
| `customer_id` | `STRING` | No | Foreign key to customer |
| `plan_id` | `STRING` | Yes | SaaS plan / tier identifier |
| `plan_name` | `STRING` | Yes | Human-readable plan name |
| `mrr_amount` | `STRING` or `DOUBLE` | No | Monthly recurring revenue in original currency |
| `currency` | `STRING` | No | ISO currency code (may be dirty) |
| `status` | `STRING` | No | `active`, `cancelled`, `paused` |
| `billing_period_start` | `STRING` or `TIMESTAMP` | No | Dirty date formats expected |
| `billing_period_end` | `STRING` or `TIMESTAMP` | No | Dirty date formats expected |
| `quantity` | `INTEGER` or `STRING` | Yes | Seats / licenses |
| `created_at` | `STRING` or `TIMESTAMP` | No | Dirty date formats expected |
| `_ingested_at` | `TIMESTAMP` | No | Metadata per project convention |
| `_schema_version` | `INTEGER` | No | Metadata per project convention |

**ARR computation:** Sum `mrr_amount` for rows where `status = 'active'` and `billing_period_end` > current date, then multiply by 12. Convert to EUR via FX rates if needed.

### `payments.invoices`

| Column | Type (Raw) | Nullable | Notes |
|---|---|---|---|
| `invoice_id` | `STRING` | No | Primary key |
| `customer_id` | `STRING` | No | Foreign key to customer |
| `subscription_id` | `STRING` | Yes | Links to subscription; NULL for one-off invoices |
| `amount` | `STRING` or `DOUBLE` | No | Invoice total in original currency |
| `currency` | `STRING` | No | ISO currency code (may be dirty) |
| `invoice_date` | `STRING` or `TIMESTAMP` | No | Dirty date formats expected |
| `due_date` | `STRING` or `TIMESTAMP` | No | Dirty date formats expected |
| `paid_at` | `STRING` or `TIMESTAMP` | Yes | NULL if unpaid |
| `status` | `STRING` | No | `paid`, `open`, `void`, `uncollectible` |
| `line_items_json` | `STRING` | Yes | Embedded JSON array of line items |
| `created_at` | `STRING` or `TIMESTAMP` | No | Dirty date formats expected |
| `_ingested_at` | `TIMESTAMP` | No | Metadata |
| `_schema_version` | `INTEGER` | No | Metadata |

**Validation:** Invoices with `subscription_id IS NOT NULL` and `status = 'paid'` in the trailing 12 months provide a cross-check for ARR computed from subscriptions.

### `lending.loan_applications`

| Column | Type (Raw) | Nullable | Notes |
|---|---|---|---|
| `application_id` | `STRING` | No | Primary key |
| `customer_id` | `STRING` | No | Logical customer identifier |
| `company_name` | `STRING` | No | May contain mixed casing and special chars |
| `company_registration_number` | `STRING` | Yes | Empty strings instead of NULL in some rows |
| `country_code` | `STRING` | No | ISO-3166 alpha-2; some invalid values |
| `industry` | `STRING` | Yes | e.g., `SaaS` |
| `requested_amount` | `STRING` or `DOUBLE` | No | Dirty types expected |
| `currency` | `STRING` | No | ISO currency code (may be dirty) |
| `application_date` | `STRING` or `TIMESTAMP` | No | Dirty date formats expected |
| `status` | `STRING` | No | `approved`, `rejected`, `pending`, `cancelled` |
| `credit_score` | `INTEGER` or `STRING` | Yes | Some out-of-range values (e.g., `999`) |
| `risk_rating` | `STRING` | Yes | Some invalid values (e.g., `N/A`) |
| `headcount_at_application` | `INTEGER` or `STRING` | Yes | Baseline for team growth metric |
| `valuation_at_application` | `STRING` or `DOUBLE` | Yes | Baseline for valuation increase metric; in EUR |
| `arr_at_application` | `STRING` or `DOUBLE` | Yes | Self-reported ARR at time of application; in EUR |
| `created_at` | `STRING` or `TIMESTAMP` | No | Dirty date formats expected |
| `_ingested_at` | `TIMESTAMP` | No | Metadata |
| `_schema_version` | `INTEGER` | No | Metadata |

### `lending.credit_facilities`

| Column | Type (Raw) | Nullable | Notes |
|---|---|---|---|
| `facility_id` | `STRING` | No | Primary key |
| `application_id` | `STRING` | Yes | Foreign key to loan_applications |
| `customer_id` | `STRING` | No | Foreign key to customer |
| `facility_limit` | `STRING` or `DOUBLE` | No | Approved limit in stated currency; dirty types expected |
| `currency` | `STRING` | No | ISO currency code (may be dirty) |
| `approval_date` | `STRING` or `TIMESTAMP` | No | Dirty date formats expected |
| `maturity_date` | `STRING` or `TIMESTAMP` | Yes | Facility end date |
| `status` | `STRING` | No | `active`, `closed`, `suspended` |
| `interest_rate` | `STRING` or `DOUBLE` | Yes | Annual rate as decimal (e.g., `0.12` = 12 %) |
| `repayment_schedule_json` | `STRING` | Yes | Embedded JSON array of scheduled repayments |
| `created_at` | `STRING` or `TIMESTAMP` | No | Dirty date formats expected |
| `_ingested_at` | `TIMESTAMP` | No | Metadata |
| `_schema_version` | `INTEGER` | No | Metadata |

**Note:** A customer may have multiple facilities over time (renewals, top-ups). The `status` column distinguishes active from closed facilities.

### `lending.drawdowns`

| Column | Type (Raw) | Nullable | Notes |
|---|---|---|---|
| `drawdown_id` | `STRING` | No | Primary key |
| `facility_id` | `STRING` | No | Foreign key to credit_facilities |
| `customer_id` | `STRING` | No | Foreign key to customer |
| `amount` | `STRING` or `DOUBLE` | No | Drawdown amount; dirty types expected |
| `currency` | `STRING` | No | ISO currency code (may be dirty) |
| `drawdown_date` | `STRING` or `TIMESTAMP` | No | Dirty date formats expected |
| `purpose` | `STRING` | Yes | e.g., `working_capital`, `expansion` |
| `status` | `STRING` | No | `completed`, `pending`, `failed` |
| `created_at` | `STRING` or `TIMESTAMP` | No | Dirty date formats expected |
| `_ingested_at` | `TIMESTAMP` | No | Metadata |
| `_schema_version` | `INTEGER` | No | Metadata |

### `lending.repayments`

| Column | Type (Raw) | Nullable | Notes |
|---|---|---|---|
| `repayment_id` | `STRING` | No | Primary key |
| `drawdown_id` | `STRING` | No | Foreign key to drawdowns |
| `facility_id` | `STRING` | No | Foreign key to credit_facilities |
| `customer_id` | `STRING` | No | Foreign key to customer |
| `scheduled_amount` | `STRING` or `DOUBLE` | No | Expected repayment amount |
| `actual_amount` | `STRING` or `DOUBLE` | Yes | NULL if not yet paid |
| `currency` | `STRING` | No | ISO currency code (may be dirty) |
| `due_date` | `STRING` or `TIMESTAMP` | No | Dirty date formats expected |
| `actual_date` | `STRING` or `TIMESTAMP` | Yes | NULL if unpaid |
| `status` | `STRING` | No | `scheduled`, `paid`, `overdue`, `forgiven` |
| `created_at` | `STRING` or `TIMESTAMP` | No | Dirty date formats expected |
| `_ingested_at` | `TIMESTAMP` | No | Metadata |
| `_schema_version` | `INTEGER` | No | Metadata |

### `banking.fx_transactions`

| Column | Type (Raw) | Nullable | Notes |
|---|---|---|---|
| `transaction_id` | `STRING` | No | Primary key |
| `customer_id` | `STRING` | No | Foreign key to customer |
| `base_currency` | `STRING` | No | e.g., `EUR` (may be dirty) |
| `quote_currency` | `STRING` | No | e.g., `GBP` (may be dirty) |
| `base_amount` | `STRING` or `DOUBLE` | No | Amount in base currency; dirty types expected |
| `quote_amount` | `STRING` or `DOUBLE` | Yes | NULL if not pre-computed by bank |
| `rate` | `STRING` or `DOUBLE` | No | FX rate; may be stored as inverse in some batches |
| `rate_type` | `STRING` | Yes | `spot`, `forward` — may be missing (schema drift) |
| `transaction_date` | `STRING` or `TIMESTAMP` | No | Dirty date formats expected |
| `counterparty_bank_bic` | `STRING` | Yes | May be missing in some batches (schema drift) |
| `created_at` | `STRING` or `TIMESTAMP` | No | Dirty date formats expected |
| `_ingested_at` | `TIMESTAMP` | No | Metadata |
| `_schema_version` | `INTEGER` | No | Metadata |

### `banking.account_balances`

| Column | Type (Raw) | Nullable | Notes |
|---|---|---|---|
| `snapshot_id` | `STRING` | No | Primary key (or composite of customer+account+date) |
| `customer_id` | `STRING` | No | Foreign key; may be orphaned in dirty data |
| `account_id` | `STRING` | No | Internal account identifier |
| `currency` | `STRING` | No | ISO currency code (may be dirty) |
| `balance` | `STRING` or `DOUBLE` | No | Account balance; dirty types expected |
| `snapshot_date` | `STRING` or `TIMESTAMP` | No | Dirty date formats; timezone offsets may vary |
| `account_type` | `STRING` | Yes | `operating`, `reserve`, `fx` |
| `created_at` | `STRING` or `TIMESTAMP` | No | Dirty date formats expected |
| `_ingested_at` | `TIMESTAMP` | No | Metadata |
| `_schema_version` | `INTEGER` | No | Metadata |

### `crm.company_metrics`

| Column | Type (Raw) | Nullable | Notes |
|---|---|---|---|
| `metric_id` | `STRING` | No | Primary key |
| `customer_id` | `STRING` | No | Foreign key to customer |
| `metric_date` | `STRING` or `TIMESTAMP` | No | Month-end snapshot date; dirty formats expected |
| `headcount` | `INTEGER` or `STRING` | Yes | Total employees |
| `valuation` | `STRING` or `DOUBLE` | Yes | Most recent valuation in EUR |
| `arr_reported` | `STRING` or `DOUBLE` | Yes | Self-reported ARR in EUR; for variance analysis |
| `created_at` | `STRING` or `TIMESTAMP` | No | Dirty date formats expected |
| `_ingested_at` | `TIMESTAMP` | No | Metadata |
| `_schema_version` | `INTEGER` | No | Metadata |

**Usage:** Enables lifecycle metrics (team growth, valuation increase) and data-quality checks comparing `arr_reported` against ARR computed from `subscriptions`.

## Raw Data Constraints — The "Dirty" Rules

Raw Parquet files must violate clean-schema assumptions in the following ways. The dbt staging layer is responsible for correcting each issue.

### 1. Inconsistent Naming & Casing
- Column names may be `camelCase`, `PascalCase`, or `snake_case` within the same entity.
- Example: `customerId`, `Customer_ID`, and `customer_id` may all appear as the same logical column across different daily batches.
- Financial-specific examples: `arr` vs `ARR` vs `annual_recurring_revenue`; `drawdownAmt` vs `drawdown_amount`.

### 2. Mixed Data Types
- The same column may be written as `STRING`, `INTEGER`, or `DOUBLE` across batches.
- Example: `facility_limit` might be `"500000"` (string) in one file and `500000.00` (double) in another.
- Amounts may be stored in minor currency units (cents) in some files and in major units (euros/dollars) in others.

### 3. Embedded JSON & Arrays
- Complex fields are stored as raw JSON strings rather than native structs or arrays.
- Example: `repayment_schedule` contains `'[{"due_date": "2026-04-01", "amount": 12500.00}, ...]'` as a VARCHAR.
- Example: `fx_rates_snapshot` stores a JSON map of currency pairs and rates as a single string column.

### 4. Invalid & Out-of-Range Values
- Dates may be in mixed formats: `MM/DD/YYYY`, `YYYY-MM-DD`, `DD-MM-YYYY`, or UNIX timestamps.
- Currency codes may contain invalid ISO values such as `EURO` instead of `EUR`, or `USD` in lowercase (`usd`).
- Negative `drawdown_amount` or negative `repayment_amount` may appear in raw files.
- `credit_score` or `risk_rating` fields may contain values outside the defined enum range (e.g., `999` or `N/A`).
- Empty strings (`''`) used instead of `NULL` for missing `company_registration_number`.

### 5. Duplicates & Missing Primary Keys
- Some rows may lack a primary key entirely (`NULL` `application_id` or `transaction_id`).
- Duplicate primary keys may appear across batches (re-ingestion, API retries, or ledger re-syncs).
- No guaranteed uniqueness at the raw layer.

### 6. Orphaned Foreign Keys
- `drawdowns` may reference `facility_id` values that do **not** exist in `credit_facilities`.
- `repayments` may reference `drawdown_id` values missing from `drawdowns`.
- `account_balances` may reference `customer_id` values that have not yet landed in `loan_applications`.

### 7. Extra & Missing Columns
- Some daily batches may contain columns that others do not (schema drift).
- Example: `credit_facilities` gains a new `collateral_required` boolean column midway through the month.
- Example: `fx_transactions` temporarily drops the `counterparty_bank_bic` column in one batch.
- All raw writes must include `_ingested_at` (timestamp) and `_schema_version` (integer) as per project convention.

### 8. Inconsistent Currency & Units
- Monetary amounts may be in minor units (cents, integer) in some files and in major units (double) in others.
- `account_balances` may omit or arbitrarily include timezone offsets in `snapshot_date`.
- Exchange rates may be stored as inverse rates (`1 / rate`) in some batches and direct rates in others.
- Currency pair notation may be inconsistent: `EURUSD` vs `EUR/USD` vs `USD_EUR`.

## Target Consumption Format

After the dbt pipeline runs, the data must resolve into clean models ready for BI, credit-risk reporting, and regulatory dashboards.

### Layer Mapping

| Layer | Prefix | Responsibility | Example Models |
|---|---|---|---|
| Staging | `stg_` | Type casting, deduplication, snake_case standardization, basic cleansing, ISO currency normalization | `stg_payments__subscriptions`, `stg_lending__drawdowns` |
| Intermediate | `int_` | Business rules, join validation, orphan handling, ARR aggregation, FX rate harmonization | `int_arr_per_customer`, `int_facility_utilization` |
| Marts | `fct_` / `dim_` | Final fact and dimension tables for dashboards and regulatory exports | `fct_drawdowns`, `dim_customers`, `fct_fx_transactions` |

### Staging Requirements (`stg_`)
- All columns renamed to `snake_case`.
- Primary keys deduplicated (keep latest by `_ingested_at`).
- Data types explicitly cast:
  - Monetary amounts → `DECIMAL(18,2)` in major currency units.
  - Dates and timestamps → `TIMESTAMP` in UTC.
  - Currency codes → uppercase `CHAR(3)` and validated against a known ISO list (`error` on unrecognized).
- Embedded JSON parsed into native ARRAY/STRUCT where applicable (e.g., repayment schedules).
- Invalid currency codes coerced to `NULL` and flagged.
- Negative amounts coerced to `NULL` or `0` based on semantic rules (a drawdown cannot be negative; a repayment reversal might be legitimate if labeled correctly).
- Empty strings coerced to `NULL`.
- Every staging model must have an `error`-level uniqueness test on its primary key.

### Intermediate Requirements (`int_`)
- Join keys validated; orphaned foreign keys kept but flagged with an `is_orphaned` boolean.
- ARR computed per customer from `subscriptions` and joined to `credit_facilities` for utilization metrics.
- `int_repayment_schedule` exploded from JSON arrays into a normalized table (`facility_id`, `drawdown_id`, `due_date`, `scheduled_amount`, `currency`).
- Currency pairs normalized to a single canonical format (`BASEQUOTE`, e.g., `EURUSD`).
- FX rates harmonized (inverse rates inverted so all rows represent `quote / base`).

### Mart Requirements (`fct_` / `dim_`)
- `fct_drawdowns` grain = one row per drawdown. Contains degenerate dimensions and foreign keys to `dim_customers` and `dim_credit_facilities`. Includes `days_since_facility_approval`.
- `fct_repayments` grain = one row per repayment event. Tracks `scheduled_vs_actual` lag in days.
- `fct_fx_transactions` grain = one row per FX conversion. Includes normalized `base_currency`, `quote_currency`, `notional_base`, `notional_quote`, and `effective_rate`.
- `dim_customers` grain = one row per customer (SaaS company). Fields:
  - **Sourced from `loan_applications` (latest approved):** `company_name`, `country_code`, `industry`, `headcount_at_application`, `valuation_at_application`
  - **Computed from `subscriptions` / `invoices`:** `lifetime_arr` (rolling 12-month), `arr_growth_pct`
  - **Computed from `credit_facilities`:** `total_facility_limit` (sum of active facility limits)
  - **Computed from `drawdowns`:** `total_drawn_amount` (sum of all completed drawdowns across all historical facilities)
  - **Computed from `banking.account_balances`:** `primary_account_currency` (currency with highest average daily balance)
  - **Computed from `crm.company_metrics` (latest):** `current_headcount`, `current_valuation`, `team_growth_pct`, `valuation_increase_multiple`
  - **Data quality:** `arr_variance_pct` = `(arr_reported - computed_arr) / computed_arr * 100`
- `dim_credit_facilities` grain = one row per approved facility. Includes:
  - `facility_limit`
  - `current_utilization_pct` (computed from drawdowns against this specific facility)
  - `facility_status` (active, closed, suspended)
- All fact tables have `not_null` and `relationships` tests on join keys (`severity: error`).

## Test Scenarios the Dummy Data Must Trigger

| Scenario | Raw Data Behavior | Expected dbt Test |
|---|---|---|
| Duplicate PK | Same `drawdown_id` in two batches | Uniqueness test on `stg_lending__drawdowns` |
| Null PK | `transaction_id IS NULL` in some FX rows | `not_null` test after filtering |
| Orphan facility | `facility_id` in drawdowns not in credit_facilities | `relationships` test (warn) + `is_orphaned` flag |
| Type drift | `facility_limit` string vs double across files | Successful cast in staging model |
| Negative amount | `drawdown_amount = -10000` | Cleansed to `NULL` or `0` in staging |
| Schema drift | New `collateral_required` column appears in facilities | Backfill with `NULL`; staging model adapts |
| Invalid date | `created_at = "13/45/2026"` | Coerced to `NULL`; freshness test may warn |
| Invalid currency | `currency = "EURO"` or `currency = "usd"` | Coerced to `NULL`; accepted-values test warns |
| Orphan customer | Drawdown references a `customer_id` never seen in applications | `relationships` test (warn) + `is_orphaned` flag |
| Inverse FX rate | `fx_rate = 0.85` stored as `1/0.85` in some batches | Harmonized to direct rate in intermediate model |
| ARR variance | `crm.company_metrics.arr_reported` differs from computed ARR by > 10 % | Custom test warns on significant self-reporting variance |

## File Format & Delivery Spec

- **Format:** Parquet, Snappy compression
- **Layout:** Hive partitioning: `year={yyyy}/month={mm}/day={dd}/`
- **Minimum batch size:** 1 file per entity per day
- **Total volume (test scope):** ~30 days of history, ≤ 100 MB total
- **Required metadata columns in every file:**
  - `_ingested_at` (TIMESTAMP) — wall-clock time of write
  - `_schema_version` (INTEGER) — start at `1`; increment on breaking schema changes

## Generated Parquet Schemas

The following schemas represent the **actual Parquet column types** as written by the generator (seed=42, days=30). Because dirty-data transformations are applied per batch, column names and types **vary across daily files** within the same entity. The schemas below show a representative single-day file for each entity.

> **Important for dbt staging models:** Column names must be normalized to `snake_case` before type casting. The dirty variants shown in the "Dirty Pattern" column appear unpredictably across different daily files.

### `payments/subscriptions`

File pattern: `payments/subscriptions/year=YYYY/month=MM/day=DD/payments_subscriptions_YYYYMMDD.parquet`

| Column | Parquet Type | Nullable | Dirty Pattern |
|---|---|---|---|
| `subscription_id` | `large_string` | yes | May appear as `subscriptionId`, `SubscriptionID` |
| `customer_id` | `large_string` | yes | May appear as `customerId`, `Customer_ID` |
| `plan_id` | `large_string` | yes | Clean in most batches |
| `plan_name` | `large_string` | yes | Clean |
| `mrr_amount` | `double` | yes | Some batches: `string` (cents), `int64` (cents), or `string` (major units); see `mrrAmount`, `MRR_Amount` |
| `currency` | `large_string` | yes | Contains invalid codes: `EURO`, `usd`, `euro`, `SEKr`, `Pounds`, `""` |
| `status` | `large_string` | yes | `active`, `cancelled`, `paused` |
| `billing_period_start` | `large_string` | yes | Mixed date formats: ISO, `MM/DD/YYYY`, `DD-MM-YYYY`, UNIX timestamp |
| `billing_period_end` | `large_string` | yes | Mixed date formats |
| `quantity` | `int64` | yes | Clean |
| `created_at` | `large_string` | yes | Mixed date formats; may appear as `createdAt`, `Created_At` |
| `_ingested_at` | `timestamp[us]` | yes | Clean; some rows backdated 45+ days for freshness testing |
| `_schema_version` | `int64` | yes | Always `1` |

### `payments/invoices`

File pattern: `payments/invoices/year=YYYY/month=MM/day=DD/payments_invoices_YYYYMMDD.parquet`

| Column | Parquet Type | Nullable | Dirty Pattern |
|---|---|---|---|
| `invoice_id` | `large_string` | yes | May appear as `invoiceId`, `Invoice_ID` |
| `customer_id` | `large_string` | yes | May appear as `customerId`, `Customer_ID` |
| `subscription_id` | `large_string` | yes | May appear as `subscriptionId`, `SubscriptionID`; NULL for one-off invoices |
| `amount` | `double` | yes | Some batches: `string` or `int64` (cents) |
| `currency` | `large_string` | yes | Invalid codes as above |
| `invoice_date` | `large_string` | yes | Mixed date formats |
| `due_date` | `large_string` | yes | Mixed date formats |
| `paid_at` | `string` | yes | Mixed date formats; NULL if unpaid |
| `status` | `large_string` | yes | `paid`, `open`, `void`, `uncollectible` |
| `line_items_json` | `large_string` | yes | Embedded JSON array |
| `created_at` | `large_string` | yes | Mixed date formats |
| `_ingested_at` | `timestamp[us]` | yes | Some rows backdated |
| `_schema_version` | `int64` | yes | Always `1` |

### `lending/loan_applications`

File pattern: `lending/loan_applications/year=YYYY/month=MM/day=DD/lending_loan_applications_YYYYMMDD.parquet`

| Column | Parquet Type | Nullable | Dirty Pattern |
|---|---|---|---|
| `application_id` | `large_string` | yes | May appear as `applicationId`, `ApplicationID` |
| `customer_id` | `large_string` | yes | Orphaned IDs for rejected/pending applications |
| `company_name` | `large_string` | yes | Mixed casing |
| `company_registration_number` | `large_string` | yes | Empty strings `""` instead of NULL |
| `country_code` | `large_string` | yes | May appear as `countryCode`, `Country_Code` |
| `industry` | `large_string` | yes | Clean |
| `requested_amount` | `double` | yes | Some batches: `string` or `int64`; may appear as `facilityLimit` |
| `currency` | `large_string` | yes | Invalid codes as above |
| `application_date` | `large_string` | yes | Mixed date formats |
| `status` | `large_string` | yes | `approved`, `rejected`, `pending`, `cancelled` |
| `credit_score` | `int64` | yes | ~2 % contain out-of-range values: `999`, `0`, `-50`, `1000` |
| `risk_rating` | `large_string` | yes | `low`, `medium`, `high`, or `N/A` |
| `headcount_at_application` | `int64` | yes | Clean |
| `valuation_at_application` | `int64` | yes | Clean |
| `arr_at_application` | `int64` | yes | Clean |
| `created_at` | `large_string` | yes | Mixed date formats |
| `_ingested_at` | `timestamp[us]` | yes | Some rows backdated |
| `_schema_version` | `int64` | yes | Always `1` |
| `referral_source` | `large_string` | yes | **Schema drift:** only present in some batches |

### `lending/credit_facilities`

File pattern: `lending/credit_facilities/year=YYYY/month=MM/day=DD/lending_credit_facilities_YYYYMMDD.parquet`

| Column | Parquet Type | Nullable | Dirty Pattern |
|---|---|---|---|
| `facility_id` | `large_string` | yes | May appear as `facilityId`, `Facility_ID` |
| `application_id` | `null` | yes | Always NULL in current data; staging layer should join when available |
| `customer_id` | `large_string` | yes | May appear as `customerId` |
| `facility_limit` | `double` | yes | Some batches: `string` or `int64` (cents); ~1 % negative values; may appear as `facilityLimit` |
| `currency` | `large_string` | yes | Invalid codes as above |
| `approval_date` | `large_string` | yes | Mixed date formats |
| `maturity_date` | `large_string` | yes | Mixed date formats |
| `status` | `large_string` | yes | `active`, `closed`, `suspended` |
| `interest_rate` | `double` | yes | Clean (decimal, e.g., `0.12` = 12 %) |
| `repayment_schedule_json` | `large_string` | yes | Embedded JSON array |
| `created_at` | `large_string` | yes | Mixed date formats |
| `_ingested_at` | `timestamp[us]` | yes | Some rows backdated |
| `_schema_version` | `int64` | yes | Always `1` |
| `collateral_required` | — | — | **Schema drift:** only present in some batches as `bool` |

### `lending/drawdowns`

File pattern: `lending/drawdowns/year=YYYY/month=MM/day=DD/lending_drawdowns_YYYYMMDD.parquet`

| Column | Parquet Type | Nullable | Dirty Pattern |
|---|---|---|---|
| `drawdown_id` | `large_string` | yes | ~2 % NULL; may appear as `drawdownId`, `Drawdown_ID`; ~4 % duplicate rows |
| `facility_id` | `large_string` | yes | ~5 % orphaned (reference non-existent facility); may appear as `facilityId` |
| `customer_id` | `large_string` | yes | May appear as `customerId` |
| `amount` | `double` | yes | Some batches: `string` or `int64` (cents); ~3 % negative values |
| `currency` | `large_string` | yes | Invalid codes as above |
| `drawdown_date` | `large_string` | yes | Mixed date formats |
| `purpose` | `large_string` | yes | `working_capital`, `expansion`, `marketing`, `hiring`, or NULL |
| `status` | `large_string` | yes | `completed` (~75 %), `pending` (~23 %), `failed` (<2 %) |
| `created_at` | `large_string` | yes | Mixed date formats |
| `_ingested_at` | `timestamp[us]` | yes | Some rows backdated |
| `_schema_version` | `int64` | yes | Always `1` |

### `lending/repayments`

File pattern: `lending/repayments/year=YYYY/month=DD/day=DD/lending_repayments_YYYYMMDD.parquet`

| Column | Parquet Type | Nullable | Dirty Pattern |
|---|---|---|---|
| `repayment_id` | `large_string` | yes | May appear as `repaymentId`, `Repayment_ID` |
| `drawdown_id` | `large_string` | yes | ~2 % orphaned (reference non-existent drawdown) |
| `facility_id` | `large_string` | yes | May reference orphaned facility |
| `customer_id` | `large_string` | yes | May appear as `customerId` |
| `scheduled_amount` | `double` | yes | Some batches: `string` or `int64` (cents); may appear as `scheduledAmt` |
| `actual_amount` | `double` | yes | NULL if not yet paid; some batches: `string` or `int64` |
| `currency` | `large_string` | yes | Invalid codes as above |
| `due_date` | `large_string` | yes | Mixed date formats |
| `actual_date` | `string` | yes | Mixed date formats; NULL if unpaid |
| `status` | `large_string` | yes | `paid` (~85 %), `scheduled`, `overdue`, `forgiven` |
| `created_at` | `large_string` | yes | Mixed date formats |
| `_ingested_at` | `timestamp[us]` | yes | Some rows backdated |
| `_schema_version` | `int64` | yes | Always `1` |

### `banking/fx_transactions`

File pattern: `banking/fx_transactions/year=YYYY/month=MM/day=DD/banking_fx_transactions_YYYYMMDD.parquet`

| Column | Parquet Type | Nullable | Dirty Pattern |
|---|---|---|---|
| `transaction_id` | `large_string` | yes | May appear as `transactionId`, `Transaction_ID` |
| `customer_id` | `large_string` | yes | May appear as `customerId` |
| `base_currency` | `large_string` | yes | Valid ISO codes in current data |
| `quote_currency` | `large_string` | yes | Valid ISO codes in current data |
| `base_amount` | `int64` | yes | Some batches: `string` (cents) or `double` (major units); may appear as `baseAmount` |
| `quote_amount` | `double` | yes | NULL if not pre-computed |
| `rate` | `double` | yes | ~5 % stored as inverse (`1/rate`) |
| `rate_type` | `large_string` | yes | `spot` or `forward`; ~10 % NULL (schema drift) |
| `transaction_date` | `large_string` | yes | Mixed date formats |
| `counterparty_bank_bic` | `large_string` | yes | **Schema drift:** column may be absent in some batches |
| `created_at` | `large_string` | yes | Mixed date formats |
| `_ingested_at` | `timestamp[us]` | yes | Some rows backdated |
| `_schema_version` | `int64` | yes | Always `1` |

### `banking/account_balances`

File pattern: `banking/account_balances/year=YYYY/month=MM/day=DD/banking_account_balances_YYYYMMDD.parquet`

| Column | Parquet Type | Nullable | Dirty Pattern |
|---|---|---|---|
| `snapshot_id` | `large_string` | yes | May appear as `snapshotId`, `Snapshot_ID` |
| `customer_id` | `large_string` | yes | ~2 % orphaned (reference unknown customers) |
| `account_id` | `large_string` | yes | Format: `acct_{uuid_prefix}_{1-3}` |
| `currency` | `large_string` | yes | Invalid codes as above |
| `balance` | `int64` | yes | Some batches: `string` (cents) or `double` (major units) |
| `snapshot_date` | `large_string` | yes | Mixed date formats; timezone offsets may vary |
| `account_type` | `large_string` | yes | `operating`, `reserve`, `fx` |
| `created_at` | `large_string` | yes | Mixed date formats |
| `_ingested_at` | `timestamp[us]` | yes | Some rows backdated |
| `_schema_version` | `int64` | yes | Always `1` |

### `crm/company_metrics`

File pattern: `crm/company_metrics/year=YYYY/month=MM/day=DD/crm_company_metrics_YYYYMMDD.parquet`

| Column | Parquet Type | Nullable | Dirty Pattern |
|---|---|---|---|
| `metric_id` | `large_string` | yes | May appear as `metricId`, `Metric_ID` |
| `customer_id` | `large_string` | yes | May appear as `customerId` |
| `metric_date` | `large_string` | yes | Mixed date formats |
| `headcount` | `int64` | yes | Clean |
| `valuation` | `int64` | yes | Some batches: `string` or `double` |
| `arr_reported` | `int64` | yes | May appear as `ARR_Reported`, `arrReported`; ~30 % differ from computed ARR by ±15 % |
| `created_at` | `large_string` | yes | Mixed date formats |
| `_ingested_at` | `timestamp[us]` | yes | Some rows backdated |
| `_schema_version` | `int64` | yes | Always `1` |

### Key Observations for dbt Staging Models

1. **All `large_string` date columns** must be parsed with a format-aware function that tries `YYYY-MM-DD`, `MM/DD/YYYY`, `DD-MM-YYYY`, `DD/MM/YYYY`, and UNIX timestamps.
2. **Mixed monetary types** across daily batches: a single column may be `double` in one file, `int64` (cents) in another, or `large_string` in a third. Staging models must cast all variants to `DECIMAL(18,2)` in major currency units.
3. **Column name casing** varies per file. The staging layer must normalize `customerId` → `customer_id`, `facilityId` → `facility_id`, `ARR_Reported` → `arr_reported`, etc.
4. **Schema drift columns** (`collateral_required`, `referral_source`) appear only in some batches. Staging models should `COALESCE` or default them to `NULL` when absent.
5. **`_ingested_at`** is a true `timestamp[us]` and can be trusted for deduplication (keep latest). All other date columns are `large_string` and require parsing.
6. **`application_id`** in `credit_facilities` is typed as `null` because all values are `None`. The staging model should still define the column as `STRING` nullable.

## Output Formats

The generator supports two output formats, selected via the `--format` flag. The **raw_events** format is the recommended default for dbt ingestion pipelines.

### Format 1: `raw_events` (Recommended)

One row per individual record with a unified schema. All entity-specific columns are packed into a JSON `data` column. This mirrors how Airbyte, dlt, and Fivetran land API data.

**File pattern:** `raw_events/year=YYYY/month=MM/day=DD/raw_events_{source}_{entity}_YYYYMMDD.parquet`

**Schema (identical for all 9 entities):**

| Column | Parquet Type | Nullable | Description |
|---|---|---|---|
| `_source` | `large_string` | no | Source system: `payments`, `lending`, `banking`, or `crm` |
| `_entity` | `large_string` | no | Entity name: e.g., `subscriptions`, `drawdowns` |
| `_ingested_at` | `timestamp[us]` | no | Wall-clock time of write; used for deduplication |
| `_schema_version` | `int64` | no | Schema version; starts at `1` |
| `_batch_id` | `large_string` | no | Unique batch identifier: `{source}_{entity}_{date}_{hex}` |
| `data` | `large_string` | no | JSON object containing all entity-specific fields (dirty data) |

**dbt staging pattern:**

```sql
-- Example: extract subscriptions from raw_events
SELECT
    _source,
    _entity,
    _ingested_at,
    _schema_version,
    _batch_id,
    json_extract(data, '$.subscription_id')  AS subscription_id,
    json_extract(data, '$.customer_id')      AS customer_id,
    json_extract(data, '$.mrr_amount')       AS mrr_amount,
    json_extract(data, '$.currency')          AS currency,
    -- ... more columns
FROM raw_events
WHERE _source = 'payments' AND _entity = 'subscriptions'
```

### Format 2: `flat` (Legacy)

One Parquet file per entity per day, with entity-specific columns as top-level columns. This is the traditional Hive-partitioned layout.

**File pattern:** `{source}/{entity}/year=YYYY/month=MM/day=DD/{source}_{entity}_YYYYMMDD.parquet`

**Schema:** Entity-specific columns as described in the "Generated Parquet Schemas" section above.

### Format 3: `both`

Writes both formats simultaneously. Useful during migration from flat to raw_events.

### Usage

```bash
# Default: raw_events format only
python3 ingestion/scripts/generate_dummy_data.py --output-dir ./data --seed 42

# Flat format only (legacy)
python3 ingestion/scripts/generate_dummy_data.py --output-dir ./data --seed 42 --format flat

# Both formats
python3 ingestion/scripts/generate_dummy_data.py --output-dir ./data --seed 42 --format both
```

## Generating the Data

A Python script (using `pyarrow` + `Faker`) will generate the raw files. The generator must accept a "dirtiness seed" so the same reproducible anomalies are injected every CI run. The generation script lives in `ingestion/scripts/generate_dummy_data.py`.

## Validation Checklist

Before the dummy data is considered ready for pipeline testing:

- [ ] Raw files written to S3 (or local MinIO) in the correct path layout.
- [ ] `dbt source freshness` fails or warns on at least one intentionally stale partition.
- [ ] `dbt test` runs in CI and surfaces both `error` and `warn` severity results.
- [ ] Metabase can connect to the DuckDB `prod.duckdb` file and render a simple "drawdowns over time" chart without errors.
- [ ] A sample ARR-to-facility-limit ratio query returns correct decimal results (validates currency normalization).
- [ ] `dim_customers.lifetime_arr` matches the sum of active subscription MRR × 12 within 1 % tolerance.
- [ ] `dim_customers.total_drawn_amount` equals the sum of all completed drawdowns per customer.
- [ ] At least one customer shows `arr_variance_pct` ≠ 0 because `crm.company_metrics.arr_reported` was intentionally seeded to differ from computed ARR.
- [ ] Multi-currency customers (e.g., `IS` / `ISK`, `GB` / `GBP`) show correct EUR-converted facility limits and ARR in `dim_customers`.
