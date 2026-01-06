System Design for Mutual Fund “Schedule of Investments” PDF Data Extractor
==========================================================================

1. Overview
-----------

Mutual funds publish PDF reports (quarterly, semi-annual, annual) with heterogeneous layouts. The objective is to build a configurable, scalable system that extracts structured data from the **“Schedule of Investments”** section across many fund families (e.g., Hartford, GSAM, BlackRock).

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

Sample reports:

- Hartford Balanced Income Fund semi-annual report:  
  `https://hartfordfunds.prospectus-express.com/summary.asp?doctype=semi&clientid=hartfordll&fundid=416648244&lpos=416648244_semi`
- GSAM semi-annual report example:  
  `https://www.gsam.com/bin/gsam/servlets/LiteratureViewerServlet?pdflink=/content/dam/gsam/pdfs/us/en/prospectus-and-regulatory/semi-annual-report/fundamental-intl-equity-sar.pdf&RequestURI=/content/gsam/us/en/advisors/fund-centre/fund-docs.html&sa=n`
- BlackRock international fund report example:  
  `https://www.blackrock.com/us/individual/resources/regulatory-documents/stream-document?stream=reg&product=MF_INTLE&shareClass=CLASS+A&documentId=920345%7E1831066%7E1831060%7E2165904%7E2118855%7E1858616%7E1858642&iframeUrlOverride=%2Fus%2Findividual%2Fliterature%2Ffirst-quarter-report%2Ffqr-retail-blackrock-international-fund.pdf`


2. High-Level Architecture
--------------------------

Key idea: a **configuration-driven pipeline** that separates:

- Generic PDF parsing and table extraction.
- Fund-specific **layout profiles** (YAML/JSON configs).
- A **validation + manual review** layer.
- **Selective AI/ML** only where deterministic rules are insufficient.

Main components:

1. Ingestion & Preprocessing
2. Fund/Layout Identification
3. Layout Profiles (Configuration Layer)
4. Table Detection & Extraction
5. Field Mapping & Normalization
6. Validation & Quality Checks
7. Manual Review UI / Tooling
8. Export & Integration


3. Component Design
-------------------

### 3.1 Ingestion & Preprocessing

Responsibilities:

- Accept PDFs via:
  - File upload (CLI, web UI, batch job).
  - URL (e.g., the Hartford / GSAM / BlackRock links above).
- Store raw PDFs with metadata: source URL, timestamp, fund family if known.
- Run a PDF processing stack:
  - Primary: text and table extraction (`pdfplumber`, `pdfminer.six`, `camelot`, or `tabula-py`).
  - Optional fallback: OCR (e.g., Tesseract) for scanned PDFs (may be out of scope for prototype).
- Normalize output into an **intermediate representation (IR)**:
  - Pages with:
    - Text blocks + coordinates.
    - Table candidates (cells with row/column indices, coordinates).

Outputs:

- IR in a structured format (e.g., JSON) for downstream components.


### 3.2 Fund / Layout Identification

Goal: determine which **layout profile** to use for a given PDF.

Approach:

- **Heuristics**:
  - Search for distinctive phrases on first N pages:
    - “The Hartford Balanced Income Fund”, “Hartford Funds”.
    - “Goldman Sachs”, “GSAM”.
    - “BlackRock International Fund”, “BlackRock”.
  - Identify report type (annual, semi-annual, etc.) via known phrases.
- **Optional classifier**:
  - Simple text-based classifier mapping PDFs to a known `layout_profile_id`.

Output:

- `layout_profile_id` (e.g., `hartford_balanced_income_v1`, `gsam_fundamental_equity_v1`).


### 3.3 Layout Profiles (Configuration Layer)

A **layout profile** is a YAML/JSON configuration describing how to parse the Schedule of Investments for a particular fund layout.

Configuration fields (examples):

- **Section detection**:
  - Regex/keywords for “Schedule of Investments”.
  - Rules for start and end pages of the section.
- **Table structure**:
  - Number of columns, presence of left/right tables on same page.
  - Header row patterns:
    - E.g., “Shares or Principal Amount”, “Market Value†”.
  - Column-to-field mappings:
    - Example:
      - Column 0: `security_name`
      - Column 1: `principal_or_shares`
      - Column 2: `market_value`
      - Sector from section headers.
- **Row handling rules**:
  - Merge multi-line security names.
  - Skip rows with “Total …”, “(continued)”, footnotes.
- **Multi-column / cross-page rules**:
  - Coordinate ranges for left/right table regions.
  - Header repetition/propagation across pages.

Benefits:

- Onboarding a new fund = authoring/editing a config file, not writing parser code.
- Profiles are versioned and testable.


### 3.4 Table Detection & Extraction

Responsibilities:

- Given IR and layout profile:
  - Locate and extract the relevant tables for Schedule of Investments.

Pipeline:

1. **Locate section**:
   - Use profile header patterns to find where “Schedule of Investments” starts.
   - Traverse pages until the next major section header or end condition.
2. **Detect tables**:
   - Use table outputs from libraries (`camelot`, `tabula-py`) or coordinate heuristics.
3. **Normalize rows**:
   - Merge multi-line security descriptions (based on indentation/coordinates).
   - Propagate context fields (sector, security type) from section headers like “Airlines - 0.0%”.
4. **Handle multi-column layouts**:
   - Split page into logical left/right regions using coordinates from profile.
   - Process each region as a separate table while preserving ordering.


### 3.5 Field Mapping & Normalization

Mapping:

- Use profile’s header patterns, column indices, and section headers to map raw row cells to canonical fields.

Normalization tasks:

- **Fund-level metadata**:
  - Extract fund name and as-of date via regex from first pages.
- **Numeric fields**:
  - Strip currency symbols and commas (`$1,499,000` → `1499000.00`).
  - Distinguish “shares” vs. “principal” when columns are combined:
    - If security type is bond-like → treat as principal.
    - If equity → treat as number of shares.
- **Country and sector**:
  - Direct mapping when explicit columns exist.
  - Otherwise derive from section headers or external issuer mapping.
- **Security type**:
  - From explicit headings like “CONVERTIBLE BONDS - 0.0%”.
  - Otherwise from rules or AI (see 3.6).

Output:

- `fund_metadata`: `{ fund_name, report_date, ... }`
- `holdings`: list of `{ security_name, security_type, country_iso3, sector, shares, principal, market_value }`


### 3.6 AI/ML Assistance (Targeted)

Use AI/ML **only for ambiguous or missing pieces** to contain cost.

Use cases:

- **Security type classification**:
  - Input: security description string.
  - Output: class such as “Convertible Bond”, “Corporate Bond”, “Equity”.
- **Sector normalization**:
  - Input: raw sector/industry text.
  - Output: standardized sector (e.g., GICS-like).
- **Country inference**:
  - Input: issuer name + optional context.
  - Output: ISO3 country code with confidence.

Cost control:

- Cache predictions per input string.
- Batch AI calls for a set of holdings.
- Use lighter models where possible.


### 3.7 Validation & Quality Checks

Validation framework runs over extracted data to detect errors and low-confidence results.

Field-level validation:

- Type checks:
  - Numeric fields must parse as numbers.
  - Currency/percentage regex patterns.
- Presence rules:
  - Required fields per security type (e.g., principal for bonds).
- Range checks:
  - No negative shares/principal/market values.

Cross-row / aggregate validation:

- Compare sum of market values by section (e.g., “Convertible Bonds”) to reported totals.
- Compare sum of all holdings to fund-level totals within tolerance.
- Check for outliers (e.g., extremely large or zero values).

Consistency validation:

- Same security (by name or identifier) should have:
  - Consistent sector.
  - Consistent country.
  - Consistent security type.

Outputs:

- Validation issues per row/field.
- Confidence scores adjusted based on rule outcomes.
- Flags used by manual review UI.


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
- **Audit trail (optional)**:
  - Track corrections and users.

Prototype simplification:

- Can be implemented as a simple web app (Flask/Streamlit) or notebook UI for the challenge.


### 3.9 Export & Integration

Formats:

- JSON:
  - One file per PDF with fund metadata and holdings list.
- CSV:
  - Flat table containing holdings plus fund-level fields as columns.
- Plain text (optional) for logging/debugging.

Integration:

- Outputs can be fed into:
  - Data warehouse.
  - Analytics pipelines.
  - Portfolio management or risk systems.


4. Steps to Onboard a New Mutual Fund
-------------------------------------

Onboarding workflow:

1. **Collect sample PDFs** for the new fund (preferably multiple reports).
2. **Explore layout** with generic parser:
   - Inspect extracted tables and text to understand structure.
3. **Identify Schedule of Investments**:
   - Locate header text and page range.
4. **Analyze table layout**:
   - Number of columns.
   - Header labels.
   - Multi-column / cross-page behavior.
   - Representation of sector/security type/country.
5. **Create layout profile**:
   - Define:
     - Section detection patterns.
     - Table coordinate hints if needed.
     - Header patterns and column-to-field mappings.
     - Rules for merged rows, totals, and continuation labels.
6. **Test and iterate**:
   - Run extraction on sample PDFs.
   - Manually verify a subset of holdings.
   - Adjust configuration.
7. **Finalize and version**:
   - Commit profile to version control.
   - Add small golden datasets for regression tests.

Scaling to hundreds of funds:

- Reuse templates for fund families with similar layouts.
- Support profile inheritance:
  - Base profile for family; child profiles override specific details.
- Provide a **layout wizard** to help analysts:
  - Visually choose header row and map columns to fields.
  - Generate initial profile automatically.


5. Validation Framework (Detail)
--------------------------------

Rule types:

- **Syntactic**:
  - Regex for currencies, percentages, and dates.
- **Semantic**:
  - Security type vs. field presence (e.g., bonds should have principal).
- **Aggregate**:
  - Section/fund totals vs. sums of row values.
- **Cross-report (advanced)**:
  - Compare holdings across different periods for outlier moves.

Implementation:

- Prefer a declarative rule representation (YAML/JSON) such as:

  - `market_value: { type: number, min: 0 }`
  - `security_type: { allowed_values: ["Equity", "Convertible Bond", "Corporate Bond", ...] }`

- Allow enabling/disabling rules per layout or fund family.


6. Performance and Cost
-----------------------

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


7. Sequence Diagram (Textual Description)
----------------------------------------

Actors: User, Ingestion Service, Parser Engine, Layout Selector, Layout Profile Store, Validation Engine, Review UI, Exporter.

Workflow:

1. User uploads or schedules a PDF.
2. Ingestion Service stores the PDF and invokes Parser Engine.
3. Parser Engine parses the PDF into IR and extracts header text.
4. Parser Engine calls Layout Selector with IR and header text.
5. Layout Selector queries Layout Profile Store and returns `layout_profile_id`.
6. Parser Engine loads the profile, locates Schedule of Investments, and extracts normalized holdings and fund metadata.
7. Validation Engine runs validation rules and assigns flags/confidences.
8. Exporter writes JSON/CSV outputs.
9. (Optional) User opens Review UI:
   - UI loads extracted data and flags.
   - UI fetches PDF snippets for context.
   - User corrects issues and exports final cleaned data.


8. Pseudocode Snippets
----------------------

### 8.1 Main Pipeline

```text
function process_pdf(pdf_path_or_url):
    pdf = download_if_needed(pdf_path_or_url)
    ir = parse_pdf_to_ir(pdf)

    fund_hint = extract_fund_hint(ir)
    profile_id = select_layout_profile(fund_hint, ir)
    profile = load_profile(profile_id)

    soi_pages = locate_schedule_of_investments(ir, profile)
    raw_rows = extract_tables(soi_pages, profile)

    holdings = []
    for row in raw_rows:
        holding = map_row_to_schema(row, profile)
        holdings.append(holding)

    fund_meta = extract_fund_metadata(ir, profile)

    validated_result = validate(fund_meta, holdings)
    export_outputs(pdf, validated_result)

    return validated_result
```

### 8.2 Layout Profile Example (YAML-style)

```text
id: hartford_balanced_income_v1
section_header_patterns:
  - "Schedule of Investments"
fund_name_pattern: "^The Hartford .* Fund"
report_date_pattern: "As of ([A-Za-z]+ \\d{1,2}, \\d{4})"

tables:
  - name: main_holdings
    pages_from_section_start: 0-*
    layout: two_column
    left_table_region: { x_min: 0, x_max: 0.5 }
    right_table_region: { x_min: 0.5, x_max: 1.0 }
    header_row_match:
      contains: ["Shares or Principal Amount", "Market Value"]
    column_mappings:
      0: security_name
      1: principal_or_shares
      2: market_value
    context_from_section_headers:
      - pattern: "Airlines -"
        field: sector
        value: "Airlines"
    merge_multiline_rows: true
    skip_rows_matching:
      - "^Total"
      - "continued"
```


9. Prototype Scope and Plan
---------------------------

Language:

- Python (for strong PDF and data-wrangling ecosystem).

Libraries (example):

- `pdfplumber` or `camelot` / `tabula-py` for table extraction.
- `pandas` for tabular manipulation.

MVP features:

- Handle **Hartford Balanced Income Fund** sample PDF:
  - Extract fund name and report date.
  - Extract a subset of Schedule of Investments (e.g., Convertible Bonds section).
  - Output holdings with: `security_name`, `security_type` (if available), `principal`, `market_value`, `sector` (where straightforward).
- Implement a **single layout profile** for Hartford.
- Demonstrate basic validation (non-negative market values, simple totals check).

Stretch goals:

- Add a second layout (GSAM or BlackRock) via another profile.
- Implement a minimal **review interface** (simple web app or notebook UI).


