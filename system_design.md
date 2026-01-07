System Design for Mutual Fund “Schedule of Investments” PDF Data Extractor
==========================================================================

## 1. Overview

Mutual funds publish PDF reports (quarterly, semi-annual, annual) with heterogeneous layouts. The objective is to build a configurable, scalable system that extracts structured data from the **“Schedule of Investments”** section across many fund families (e.g., GSAM, BlackRock, and others).

The system must:

- Support **hundreds of funds** with minimal per-fund engineering effort.
- Produce **structured data outputs** (JSON/CSV/plain text) with:
  - Fund name
  - Report as-of-date
  - For each holding in Schedule of Investments:
    - Security name
    - Security type
    - Country (ISO3)
    - Sector
    - Number of shares
    - Principal
    - Market value

Example sample reports (used during prototyping and testing):

- GSAM semi-annual report example (emerging markets equity fund).
- BlackRock International Fund quarterly/annual report.


## 2. High-Level Architecture

Key idea: a **configuration-driven pipeline** that separates:

- Generic PDF parsing and table extraction.
- Fund-specific **layout profiles** (YAML/JSON configs).
- A **validation + manual review** layer.
- **Selective AI/ML** only where deterministic rules are insufficient.

Main components:

1. Ingestion & Preprocessing
2. Fund/Layout Identification
3. Layout Configs (Configuration Layer)
4. Generic Table Detection & Extraction
5. Field Mapping & Normalization
6. Validation & Quality Checks
7. Manual Review UI / Tooling (future)
8. Export & Integration
9. AI-Assisted Config Generation


## 3. Component Design

### 3.1 Ingestion & Preprocessing

Responsibilities:

- Expose APIs to accept PDFs:
  - **Report ingestion**: single or batched uploads of mutual fund reports.
  - **Config samples**: single or batched uploads of sample PDFs used to craft new layout configs.
- Store raw PDFs in an **object store** (e.g., S3/GCS/Azure Blob) with stable URLs.
- Maintain metadata in a **relational database**:
  - `reports(id, fund_family, object_url, status, as_of_date, fund_name_guess, ...)`
  - `config_samples(id, object_url, layout_id_guess, status, ...)`
- Enqueue **asynchronous jobs** for extraction or config generation when files are uploaded.
- Run a PDF processing stack inside extraction workers:
  - Primary: text extraction library (e.g., `pdfplumber`/`pdfminer`) to obtain per-page text.
  - OCR fallback for scanned/image-only PDFs (see Section 3.6).

The ingestion layer is responsible for reliably receiving files, persisting them, and handing out identifiers and URLs that other components (extraction, config generator, review UI) can use.


### 3.2 Fund / Layout Identification

Goal: determine which **layout profile** to use for a given PDF.

Approach:

- Use **heuristics** and/or a lightweight classifier on the first N pages:
  - Look for key phrases like `"Schedule of Investments"`, fund family names, or distinctive headers.
  - Match against known layout configs by `layout_id`.
- Optionally user to **force** a specific `layout_id` at ingestion time.
- Persist the selected or guessed `layout_id` in the `reports` metadata.

Output:

- `layout_id` / `layout_config` reference for the extraction workers to use.


### 3.3 Layout Configs (Configuration Layer)

A **layout config** is a YAML/JSON document describing how to parse the Schedule of Investments for a particular fund layout. These configs are stored in a central repository (e.g., database + Git-backed files) and loaded by extraction workers at runtime.

Configuration fields (examples):

- **Section detection**:
  - `schedule_header`: phrase to locate the Schedule of Investments (e.g., `"Schedule of Investments"`).
- **Table structure**:
  - `layout.type`: hints about row structure, e.g. `two_column_multiline_shares_first`.
  - `layout.columns`: number of vertical columns on each page (e.g., 1, 2, 3).
  - `layout.shares_token_index` / `layout.value_token_index`: which numeric tokens map to shares/principal vs. market value.
- **Instrument headers**:
  - `instrument_headers`: mapping from raw section headings to normalized `security_type` values.
- **Stop / noise rules**:
  - `stop_line_prefixes`: page-local prefixes that indicate the end of holdings (e.g., `"Total Long-Term Investments"`).
  - `stop_line_contains`: substrings that indicate we should stop reading holdings on that page.
  - `noise_prefixes`: lines to ignore (e.g., `(Cost: $...`, `Other Assets`, `Net Assets`).

Benefits:

- Onboarding a new fund = authoring/editing a config file, not writing parser code.


### 3.4 Generic Table Detection & Extraction

Responsibilities:

- Given a parsed PDF (text per page) and a `layout_config`, locate and extract holdings from the Schedule of Investments using a **single generic extraction engine**.

Extraction pipeline:

1. **Locate anchor pages**:
   - Scan all pages and mark those whose text contains the `schedule_header`.
2. **Expand to full range**:
   - Take the min and max anchor page indices for the schedule.
   - For every page in this inclusive range, decide whether it "looks like" a holdings page (based on header fragments and numeric-line heuristics) and include it.
3. **Column splitting**:
   - For each selected page, split it into `N` equal-width vertical regions, where `N = layout.columns`.
   - Process each region as an independent column/table to correctly handle 2–3 column layouts.
4. **Line-by-line parsing**:
   - Iterate text lines within each column region.
   - Use `stop_line_prefixes` / `stop_line_contains` as **page-local** stop conditions.
   - Use `noise_prefixes` to drop non-holding lines.
5. **Multi-line row merging**:
   - Maintain a "pending" holding while reading lines.
   - Merge multi-line security descriptions and detect when numeric tokens indicate the end of a row.
6. **Instrument/section headers**:
   - Recognize instrument headers (e.g., `"COMMON STOCKS"`) and propagate `security_type` to subsequent holdings until the next header.


### 3.5 Field Mapping & Normalization

Mapping:

- Use layout config hints (token indices, instrument headers) and simple heuristics to map numeric tokens and text segments to canonical fields.

Normalization tasks:

- **Fund-level metadata**:
  - `fund_name`: extracted from PDF text (e.g., a line ending with `"Fund"` on early pages), with `layout_id` as a fallback if text-based guessing fails.
  - `report_date`: extracted from the first pages using a regex that handles both spaced and compact dates (e.g., `"August 31, 2025"` and `"AUGUST31,2025"`).
- **Numeric fields**:
  - Strip commas and currency symbols where present.
  - Map numeric tokens according to `shares_token_index` and `value_token_index`.
- **Country**:
  - Derived from section headings and mapped to ISO3 via `COUNTRY_TO_ISO3` and `country_heading_to_iso3`.
- **Security name normalization**:
  - `_normalize_name` fixes common spacing issues:
    - Insert spaces between lowercase and uppercase transitions (e.g., `"AssaAbloy"` → `"Assa Abloy"`).
    - Normalize spaces around commas, ampersands, and parentheses (e.g., `"Toronto- Dominion Bank( The)"` → `"Toronto-Dominion Bank (The)"`).

Output:

- One `Holding` dataclass per row (`fund_extractor/models.py`) with:
  - `fund_name`, `report_date`, `security_name`, `security_type`, `country_iso3`, `sector`, `shares`, `principal`, `market_value`.


### 3.6 AI/ML Assistance

Use AI/ML **only for ambiguous or missing pieces** to save cost.

Planned use cases:

- **OCR for image-based PDFs**:
  - Run an on-prem OCR engine (e.g., Tesseract) on pages with no extractable text.
  - Optionally fall back to a cloud OCR/vision API for difficult documents.
  - Feed OCR text back into the generic extraction engine.
- **Security type and sector classification**:
  - Input: security description, optional context.
  - Output: normalized security type (e.g., “Convertible Bond”, “Equity”) and sector (e.g., GICS sector).
- **Country inference**:
  - Input: issuer name + context.
  - Output: ISO3 country code with confidence, when not obvious from headings.
- **AI-assisted layout config generation**:
  - Given a sample PDF’s text, have an LLM propose an initial layout config that a human can refine.

Cost control:

- Cache predictions per input string.
- Batch AI calls for a set of holdings or sample pages.
- Use lighter/cheaper models where possible.
- Limit AI usage to onboarding/config generation and rare fallbacks, not every extraction.


### 3.7 Validation & Quality Checks

Validation runs over extracted data to detect obvious errors and suspicious patterns, and to gate what is allowed into downstream systems.

Responsibilities:

- **Field-level validation**:
  - Type checks (numeric fields must parse as numbers, dates must parse).
  - Presence rules (e.g., `security_name` and at least one of `shares/principal/market_value`).
  - Range checks (no negative shares/principal/market values for long-only funds).
  - Format checks (valid ISO3 country codes, known sector names).
- **Aggregate validation**:
  - Compare sum of `market_value` by section/fund to reported totals (within tolerance).
  - Flag outliers (e.g., extremely large positions vs. portfolio size).

Implementation:

- A **validation service** (or library) that:
  - Accepts a batch of holdings and fund metadata.
  - Applies a configurable set of rules (some global, some per-fund layout).
  - Outputs structured results: lists of errors, warnings, and per-row flags.
- Results are persisted (e.g., `validation_results` table) and surfaced in APIs and the review UI.


### 3.8 Manual Review UI / Tooling (Concept)

Goal: let users quickly review and correct problematic rows.

Core features:

- **Row grid**:
  - Table of holdings with filters and sorting.
  - Columns include parsed fields and validation/AI flags.
- **Issue filters**:
  - Show only rows with failed validation.
  - Show only AI-inferred fields (sector/country/type).
- **PDF context panel**:
  - Display a PDF page snippet around the selected row.
  - Highlight region corresponding to the row text.
- **Inline editing**:
  - Users adjust fields directly in the grid.
  - Changes saved to corrected dataset.

### 3.9 Export

Formats:

- JSON:
  - One file per PDF containing a list of `Holding` dicts.
- CSV:
  - Flat table containing holdings plus fund-level fields as columns.


## 4. Steps to Onboard a New Mutual Fund

Onboarding workflow:

1. **Upload sample PDFs** for the new fund (preferably multiple reports) via a config-onboarding API.
2. **Generate an initial layout config with AI (optional)**:
   - A config generator service pulls the sample PDFs from object storage.
   - It extracts representative text pages and calls an LLM to propose a draft layout config for each fund/layout.
3. **Explore and refine the layout**:
   - Through a web UI, analysts review the draft YAML/JSON configs.
   - They tweak fields such as `schedule_header`, `layout.columns`, `instrument_headers`, `stop_line_prefixes`, and `noise_prefixes`.
   - Configs are saved as new versions in a central store.
4. **Test extraction**:
   - Trigger test runs for the associated sample reports using the new layout config.
   - Inspect holdings and validation results in the UI.
5. **Iterate**:
   - Adjust config fields until extraction and validation results are satisfactory.
6. **Finalize and version**:
   - Mark the config version as `active` for its layout/fund family.

Scaling to hundreds of funds:

- Reuse configs for fund families with similar layouts.
- Use the AI-based config generator to bootstrap new configs quickly, then refine manually.


## 5. Validation Framework (Detail)

Rule types:

- **Syntactic**:
  - Regex for currencies, percentages, and dates.
- **Semantic**:
  - Security type vs. field presence (e.g., bonds should have principal).
- **Aggregate**:
  - Section/fund totals vs. sums of row values.

Implementation:

- Rules can be implemented in code and optionally expressed declaratively in YAML/JSON, e.g.:

  - `market_value: { type: number, min: 0 }`
  - `security_type: { allowed_values: ["Equity", "Convertible Bond", "Corporate Bond", ...] }`

- Allow enabling/disabling rules per layout or fund family.


## 6. Performance and Cost

Performance concerns:

- Large PDFs (hundreds of pages).
- Batch processing many funds.

Optimization strategies:

- **Scope reduction**:
  - Parse only pages in or near the Schedule of Investments section.
- **Streaming**:
  - Process PDFs page-by-page where possible.
- **Parallelism**:
  - Run multiple PDFs in parallel.
  - Limited page-level parallelism within a PDF.
- **Caching**:
  - Cache IR to avoid reparsing PDFs.
  - Cache AI predictions by input string.

Cost control for AI:

- Only call AI when rules fail or fields are missing.
- Limit AI usage to specific fields (sector/country/type).
- Monitor and cap per-document usage.


## 7. Pseudocode Snippets

### 7.1 Main Pipeline

```text
function process_pdf(pdf_path_or_url, optional_layout_id):
    pdf = load_pdf(pdf_path_or_url)  # pdfplumber

    if is_image_based(pdf):
        ocr_text_by_page = ai_ocr_extract_pdf(pdf_path_or_url)  # future
        return process_with_ocr_text(ocr_text_by_page)

    text_first_pages = extract_text_first_pages(pdf)

    if optional_layout_id is not None:
        cfg = load_layout_config_by_id(optional_layout_id)
    else:
        cfg = detect_config_for_pdf(text_first_pages, all_layout_configs)

    holdings = extract_with_layout(pdf, cfg, fund_name_hint, report_date_hint)

    # Write raw extraction results; validation is run as a separate step.
    export_to_json_and_csv(holdings)

    return holdings
```

### 7.2 Layout Profile Example (YAML-style)

```text
id: blackrock_international
schedule_header: "Schedule of Investments"
layout:
  type: two_column_multiline_shares_first
  columns: 2
  shares_token_index: 0
  value_token_index: 1
instrument_headers:
  COMMON STOCKS: "Common Stock"
stop_line_prefixes:
  - "Total Long-Term Investments"
stop_line_contains: []
noise_prefixes:
  - "(Cost:$"
  - "Other Assets"
  - "Net Assets"
```

