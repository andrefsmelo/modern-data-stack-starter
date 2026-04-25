# Ingestion

> The realistic 2026 landscape for moving data from external sources into S3 / a warehouse, and how to choose between options for a company of up to ~50 employees.

This document is the deep-dive reference. The short decision rule lives in [architecture.md](architecture.md#ingestion-airbyte-vs-dlt-vs-python); use that for day-to-day calls and come here when the rule does not fit.

-----

## The five categories

Every modern ingestion tool falls into one of five buckets. Knowing the bucket is more important than knowing the tool.

1. **Managed (SaaS) ELT** — you pay, somebody else operates connectors. Examples: Fivetran, Stitch, Hevo, Estuary, Rivery, Matillion.
2. **Open-source / self-hosted ELT** — you operate the connectors. Examples: Airbyte, Meltano, Singer (raw).
3. **Code-first lightweight** — connectors are Python (or Go) you write/import, no server. Examples: dlt, Sling, Embulk.
4. **CDC / streaming** — change-data-capture from operational databases, near-real-time. Examples: Debezium, AWS DMS, Google Datastream, Estuary Flow.
5. **Unstructured / document extraction (OCR & document AI)** — when the source is a PDF, photo, scan, or other document that needs text and field extraction before it becomes a row. Examples: AWS Textract, Google Document AI, Mindee, PaddleOCR, LLM-based extraction (Claude / GPT-4o / Gemini).

Phase 1 of this stack lives in categories 2 and 3. Categories 1, 4, and 5 enter when a specific source profile demands them.

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

### Unstructured / document extraction (OCR & document AI)

When the source is a **PDF, photo, scan, fax, or any document** — invoices, receipts, contracts, ID cards, lab reports — the data is locked inside an image or a PDF that is not natively a table. You need an extraction step **before** the rest of the ELT stack sees it.

The pattern is always the same:

```
Document arrives (email attachment, upload, S3 drop)
        │
        ▼
[Landing zone]
s3://{bucket}/raw/documents/{type}/{yyyy}/{mm}/{dd}/file.pdf
        │
        ▼
[Extraction job]   ← the new step (OCR + structuring)
GitHub Actions / Lambda triggered by S3 event
        │
        ▼
[Structured output]
s3://{bucket}/raw/documents_extracted/{type}/{yyyy}/{mm}/{dd}/*.parquet
        │
        ▼
[dbt staging]      ← treats the Parquet as a normal source
```

The choice of extraction tool depends on three things: **template predictability** (always the same vs. variable per vendor), **volume**, and **data sensitivity**.

#### AWS Textract
- **What it is**: managed OCR with extras for forms, tables, and signature detection.
- **Pricing**: ~$0.0015 per page for plain text; ~$0.05 per page for tables/forms.
- **Use when**: predictable structured documents (invoices in a fixed layout, application forms) on AWS.
- **Skip when**: highly variable templates — you will spend more time on post-processing rules than the OCR itself.

#### Google Document AI
- **What it is**: same category as Textract, with **specialized parsers** for invoices, receipts, IDs, W-2s, etc. Each parser is pre-trained for that document class.
- **Pricing**: similar order of magnitude to Textract; specialized parsers cost more per page.
- **Use when**: your document type matches one of the specialized parsers — those parsers return structured fields (vendor, total, line items) without you writing extraction logic.
- **Skip when**: your document is not in the parser catalog and you don't have volume to justify training a custom parser.

#### Azure Document Intelligence (formerly Form Recognizer)
- **What it is**: Azure's equivalent. Comparable feature set; choose based on which cloud you're already on.

#### Mindee
- **What it is**: managed extraction with pre-trained APIs for common document types (invoices, receipts, IDs, bank statements).
- **Pricing**: per-document, predictable.
- **Use when**: you want a single API that returns clean JSON for common business documents and you're not committed to a specific cloud.
- **Skip when**: your documents are exotic or proprietary.

#### LLM-based extraction (Claude / GPT-4o / Gemini)
- **What it is**: send the document (PDF directly, or page images) to a multimodal LLM with a structured-output schema (JSON schema or Pydantic). The LLM does both OCR and field extraction in one call.
- **Pricing**: ~$0.01–0.05 per page depending on model and page count.
- **Strengths**: handles **highly variable templates** (50 different vendor invoice layouts) without per-template training; zero ML maintenance; trivial to add a new field — edit the schema and re-run.
- **Weaknesses**: more expensive per page than Textract for high volume; non-deterministic at the margins (need validation rules); not appropriate for highly regulated PII unless you use a HIPAA/BAA-eligible offering.
- **Use when**: document layouts vary across senders, OR you need to extract semantically rich fields (e.g. "the cancellation clause") that templated tools can't do.
- **Skip when**: volume is > 100k pages/month — managed Document AI becomes cheaper at scale.

#### PaddleOCR
- **What it is**: open-source OCR engine from Baidu. Strong multi-lingual support, includes layout detection and table recognition.
- **Use when**: data sensitivity forbids cloud APIs (regulated PII, on-prem requirements), or volume is large enough that per-page cloud pricing dominates.
- **Skip when**: you don't have someone to operate a GPU and tune the pipeline.

#### docTR / Surya / Tesseract
- **What it is**: other OSS OCR options.
  - **docTR** (Mindee, OSS): modern, end-to-end deep-learning OCR.
  - **Surya**: newer, accurate on complex layouts.
  - **Tesseract**: the classic. OK for clean printed text, weak on layout.
- **Use when**: same situations as PaddleOCR — pick on language support and benchmark on your actual documents.

#### Unstructured.io / LlamaParse / Marker / Docling
- **What they are**: document **parsers** (not pure OCR). They turn a PDF into clean structured chunks (text + tables + images) suitable for downstream processing.
- **Use when**: your PDFs are already digital (text-layer present) and the hard part is layout understanding rather than OCR.
- **Skip when**: your PDFs are scans — you still need OCR first.

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
| Source is PDFs / scans with **fixed templates** (your own forms, one vendor's invoices) | **AWS Textract** or **Azure Document Intelligence** | Cheap per page; structured-form support solves it |
| Source is PDFs from **many different senders** (50 vendor invoice layouts) | **LLM extraction** (Claude / GPT-4o) with structured-output schema | Variable layouts kill template-based tools; LLMs handle them with no per-template work |
| Source matches a Document AI **specialized parser** (W-2, receipt, ID, etc.) | **Google Document AI** | Returns clean structured fields without you writing extraction logic |
| Sensitive documents that cannot leave the network, or > 100k pages/month | **PaddleOCR** or **docTR** self-hosted | OSS removes per-page cloud cost and keeps data on-prem |
| Digital PDFs (text layer present), need clean structure not OCR | **Unstructured.io** or **Marker** | Layout parsing, not OCR, is the real problem |

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

For **document / OCR sources**, treat the extraction as a separate ingestion job that lands its structured output back in S3 as Parquet, so the rest of the stack (dbt, Metabase) sees it as a normal source. Default in 2026:

- **Variable templates** (different senders, different layouts) → **LLM extraction** (Claude or GPT-4o) with a structured-output schema. Cheapest path to working extraction without per-template tuning.
- **Fixed templates** (your own forms, one vendor) → **AWS Textract** or **Google Document AI** specialized parser.
- **Sensitive / on-prem only** → **PaddleOCR** or **docTR** self-hosted on a GPU.

Validate every extraction with downstream dbt tests (`not_null` on key fields, range checks on totals) — non-deterministic extractors slip occasionally and you want to catch it in CI, not in a dashboard.

-----

## Anti-patterns

- **Running Airbyte for one source.** The operational overhead exceeds writing 50 lines of dlt.
- **Adopting Fivetran "to save engineering time" before measuring how much time you actually spend on ingestion.** Most small teams spend < 1 day/month, which doesn't justify the bill.
- **Mixing 3+ ingestion tools "because each one is best at something."** Operational surface area compounds. Two tools is the practical maximum (one general-purpose ELT plus one specialist for an outlier source).
- **Building a custom Singer tap for a SaaS that already has a verified dlt or Airbyte connector.** Always check the existing libraries first.
- **Choosing CDC because the data team thinks it would be cool.** CDC needs an actual product reason.
- **Reaching for an LLM to extract from one fixed-template PDF you receive monthly.** Textract or Document AI is 10× cheaper and deterministic.
- **Reaching for Textract for 50 vendor invoice layouts.** You will spend more time on per-template extraction rules than the LLM call would cost.
- **Storing only the extracted fields and discarding the original document.** Always keep the raw PDF/image in S3 — re-extraction is the answer when the schema changes.

-----

## References

- [dlt — verified sources](https://dlthub.com/docs/dlt-ecosystem/verified-sources)
- [Meltano Hub](https://hub.meltano.com)
- [Airbyte connector catalog](https://docs.airbyte.com/integrations)
- [Fivetran connector catalog](https://www.fivetran.com/connectors)
- [Sling docs](https://docs.slingdata.io)
- [Singer spec](https://github.com/singer-io/getting-started)
- [AWS Textract](https://docs.aws.amazon.com/textract/)
- [Google Document AI](https://cloud.google.com/document-ai/docs)
- [Azure Document Intelligence](https://learn.microsoft.com/azure/ai-services/document-intelligence/)
- [Mindee API](https://developers.mindee.com)
- [Anthropic — PDF support](https://docs.anthropic.com/en/docs/build-with-claude/pdf-support)
- [PaddleOCR](https://github.com/PaddlePaddle/PaddleOCR)
- [docTR](https://github.com/mindee/doctr)
- [Unstructured.io](https://docs.unstructured.io)
