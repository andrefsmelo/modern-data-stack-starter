# Ingestion

> The realistic 2026 landscape for moving data from external sources into S3 / a warehouse, and how to choose between options for a company of up to ~50 employees.

This document is the deep-dive reference. The short decision rule lives in [architecture.md](architecture.md#ingestion-airbyte-vs-dlt-vs-python); use that for day-to-day calls and come here when the rule does not fit.

-----

## The four categories

Every modern ingestion tool falls into one of four buckets. Knowing the bucket is more important than knowing the tool.

1. **Managed (SaaS) ELT** — you pay, somebody else operates connectors. Examples: Fivetran, Stitch, Hevo, Estuary, Rivery, Matillion.
2. **Open-source / self-hosted ELT** — you operate the connectors. Examples: Airbyte, Meltano, Singer (raw).
3. **Code-first lightweight** — connectors are Python (or Go) you write/import, no server. Examples: dlt, Sling, Embulk.
4. **CDC / streaming** — change-data-capture from operational databases, near-real-time. Examples: Debezium, AWS DMS, Google Datastream, Estuary Flow.

Phase 1 of this stack lives in categories 2 and 3. Categories 1 and 4 enter the picture in Phase 2 or beyond.

-----

## Tool-by-tool

### Managed (SaaS)

#### Fivetran
- **What it is**: the gold standard managed ELT. 500+ connectors, near-zero operational overhead.
- **Pricing**: per "monthly active row" (MAR). Starts modest, scales steeply.
- **Use when**: engineering time costs more than the bill (typical past ~20 engineers), or you need an SLA you can point a finance team at.
- **Skip when**: budget-constrained, or your row volume is unpredictable.

#### Stitch (Talend / Qlik)
- **What it is**: cheaper Fivetran. Built on Singer underneath.
- **Pricing**: starts ~$100/mo flat, tiered by row volume.
- **Use when**: you want managed but Fivetran pricing is a non-starter.
- **Skip when**: you need connectors Stitch doesn't have (its catalog is smaller).

#### Hevo Data
- **What it is**: managed ELT with flat per-source pricing instead of per-row.
- **Use when**: you have predictable source counts and unpredictable row volumes.
- **Skip when**: you have many small sources — per-source pricing punishes that shape.

#### Estuary Flow
- **What it is**: newer entrant. Batch + CDC + streaming in one platform.
- **Use when**: you need near-real-time and don't want to operate Kafka.
- **Skip when**: pure batch is fine — the streaming features add cognitive load you don't need.

#### Rivery / Matillion
- **What it is**: heavier platforms that bundle ingestion with transformation orchestration.
- **Use when**: you specifically want a single vendor for ingest + transform + scheduling.
- **Skip when**: you've already committed to dbt for transformation. Overlap creates confusion.

### Open-source / self-hosted

#### Airbyte (OSS)
- **What it is**: 300+ connectors, web UI, JVM service plus Temporal plus a Postgres metadata DB.
- **Strengths**: large connector library, UI usable by non-engineers, schema discovery, incremental sync state, OAuth handled.
- **Weaknesses**: heavy (4 GB+ RAM minimum), upgrades occasionally break, row-by-row architecture is wrong for bulk extracts (> 10 GB/day from a single source), connector quality varies (alpha/beta tiers).
- **Use when**: you have **3+ SaaS sources with non-trivial auth** AND non-engineers will add sources later AND you have someone willing to operate the JVM.
- **Skip when**: any of those three conditions is false.

#### Meltano
- **What it is**: CLI-first, Singer-based, lots of community taps. Often described as "Airbyte without the UI and the JVM."
- **Strengths**: lightweight (Python), config in YAML and version-controlled, large tap ecosystem, runs in CI.
- **Weaknesses**: Singer tap quality is uneven; no UI for non-engineers; smaller community than Airbyte.
- **Use when**: you want pre-built connector coverage but refuse the JVM operational cost. Often the right answer that gets skipped.
- **Skip when**: non-engineers must add sources (no UI).

#### Singer taps (directly)
- **What it is**: the protocol underneath Stitch and Meltano. ~500 community taps.
- **Use when**: you want full control and a specific tap exists with good quality.
- **Skip when**: you would also benefit from any orchestration around it — at that point use Meltano, which gives you Singer plus structure.

### Code-first lightweight

#### dlt
- **What it is**: Python library. Write a generator that yields records; dlt handles schema inference, incremental state, normalization, and writing to S3 / a warehouse. No server.
- **Strengths**: zero infra, runs in GitHub Actions, growing library of "verified sources" (Stripe, HubSpot, Notion, Salesforce, GA4, etc.), genuinely lightweight.
- **Weaknesses**: smaller pre-built connector set than Airbyte; no UI; you write Python.
- **Use when**: sources are few (1–5), engineers-only, or sources are custom REST APIs.
- **Skip when**: you have 10+ SaaS sources and don't want to maintain even a small amount of glue code.

#### Sling
- **What it is**: Go binary. Excellent for **DB → warehouse** and **file → DB** moves.
- **Strengths**: very fast (Go, not row-by-row), single binary, great for Postgres → S3 / S3 → BigQuery.
- **Weaknesses**: limited SaaS connector story.
- **Use when**: most of your ingest is database replication or file movement, not SaaS APIs.
- **Skip when**: you mostly pull from SaaS tools.

#### Embulk
- **What it is**: older Java-based bulk loader.
- **Use when**: you've inherited it. Otherwise, prefer Sling or dlt.

### CDC / streaming

#### Debezium
- **What it is**: open-source CDC from Postgres / MySQL / MongoDB into Kafka.
- **Use when**: you need < 1 minute freshness and you (or your platform team) already operate Kafka.
- **Skip when**: you don't want to operate Kafka.

#### AWS DMS
- **What it is**: managed CDC on AWS. Free tier exists.
- **Use when**: you're on AWS and need DB replication without operating Kafka. Clunky UI but works.
- **Skip when**: not on AWS.

#### Google Datastream
- **What it is**: AWS DMS equivalent on GCP.

-----

## Decision matrix for a company up to ~50 employees

| Your situation | Recommended | Why |
|---|---|---|
| 1–5 SaaS sources, engineers only | **dlt** in GitHub Actions | Zero infra, runs in existing CI, verified sources cover the common SaaS tools |
| 1–5 SaaS sources, non-engineers will add some later | **Airbyte** (self-hosted) | UI matters; the operational cost is acceptable at small scale |
| 5–15 SaaS sources, engineers only, want pre-built coverage | **Meltano** | Singer tap library without the JVM; CI-friendly |
| 5–15 SaaS sources, mixed team, willing to pay | **Fivetran** or **Stitch** | Engineering time saved exceeds the bill |
| Mostly Postgres / MySQL → S3 | **Sling** or **AWS DMS** | Bulk DB movement is what they're built for |
| Need < 1 hour freshness from an operational DB | **AWS DMS** (managed) or **Debezium** (self-hosted) | This is CDC, not batch ELT |
| Predictable source count, unpredictable volume | **Hevo Data** | Per-source pricing matches your shape |
| > 100 sources or > 50 engineers | **Fivetran** | The MAR bill is now smaller than the team's time |

-----

## Recommendation for this stack

For a company up to ~50 employees in Phase 1, the realistic shortlist is **three tools**: `dlt`, `Meltano`, `Airbyte`. Pick one as the **default**, and treat the others as escape hatches:

- **Default for engineering-led teams**: `dlt`. Lightest possible footprint; runs in GitHub Actions; no extra VM bill.
- **Default for mixed teams**: `Airbyte` (self-hosted on a 4 GB VM) — only if the UI is actually being used. If the UI is not used after 3 months, retire it and migrate to dlt or Meltano.
- **Default for "I want Airbyte coverage without the JVM"**: `Meltano`. Most often skipped, frequently the right answer.

Reach for managed (Fivetran / Stitch / Hevo) when one of these fires:

- Source count > 15, or
- Engineering team > 20 (their time is now expensive enough), or
- Stakeholders demand a vendor SLA.

Reach for CDC (DMS / Debezium / Estuary) only when freshness < 1 hour is a real product requirement, not a nice-to-have. CDC is a different operational discipline — it should be a deliberate Phase 2+ decision, not a Phase 1 experiment.

-----

## Anti-patterns

- **Running Airbyte for one source.** The operational overhead exceeds writing 50 lines of dlt.
- **Adopting Fivetran "to save engineering time" before measuring how much time you actually spend on ingestion.** Most small teams spend < 1 day/month, which doesn't justify the bill.
- **Mixing 3+ ingestion tools "because each one is best at something."** Operational surface area compounds. Two tools is the practical maximum (one general-purpose ELT plus one specialist for an outlier source).
- **Building a custom Singer tap for a SaaS that already has a verified dlt or Airbyte connector.** Always check the existing libraries first.
- **Choosing CDC because the data team thinks it would be cool.** CDC needs an actual product reason.

-----

## References

- [dlt — verified sources](https://dlthub.com/docs/dlt-ecosystem/verified-sources)
- [Meltano Hub](https://hub.meltano.com)
- [Airbyte connector catalog](https://docs.airbyte.com/integrations)
- [Fivetran connector catalog](https://www.fivetran.com/connectors)
- [Sling docs](https://docs.slingdata.io)
- [Singer spec](https://github.com/singer-io/getting-started)
