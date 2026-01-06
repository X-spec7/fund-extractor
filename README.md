Prototype: Mutual Fund PDF Schedule of Investments Extractor
============================================================

This repository contains a **prototype** implementation of the system design for extracting holdings data from mutual fund PDF reports, starting with the **Hartford Balanced Income Fund** example.


1. Setup
--------

Requirements:

- Python 3.10+ (recommended)

Install Python dependencies:

```bash
cd /root/test/fund-extractor
pip3 install -r requirements.txt
```


2. Running the Hartford Prototype
---------------------------------

The main entry point is `main.py`, which currently targets the Hartford Balanced Income Fund layout.

You can provide either:

- A **local PDF path**, or
- A **direct URL** to the PDF (if accessible from your environment).

Example using the Hartford Balanced Income Fund semi-annual report URL:

```bash
python main.py "https://hartfordfunds.prospectus-express.com/summary.asp?doctype=semi&clientid=hartfordll&fundid=416648244&lpos=416648244_semi"
```

This will:

- Download and parse the PDF.
- Attempt to locate the **Schedule of Investments** section.
- Extract a subset of holdings information using Hartford-specific heuristics.
- Write:
  - `hartford_holdings.json`
  - `hartford_holdings.csv`

You can override output paths:

```bash
python main.py /path/to/hartford_report.pdf --out-json output.json --out-csv output.csv
```


3. Current Extraction Scope
---------------------------

The prototype demonstrates:

- Detection of:
  - Fund name (e.g., "The Hartford Balanced Income Fund").
  - Report date (e.g., "April 30, 2023").
- Location of the **Schedule of Investments** section by header text.
- Simple heuristics to:
  - Track **security type** from section headers such as "CONVERTIBLE BONDS".
  - Track **sector** from lines like "Airlines - 0.0%".
  - Pair security names with their corresponding **principal** and **market value** from nearby numeric columns.

The output schema per holding (JSON/CSV) is:

- `fund_name`
- `report_date`
- `security_name`
- `security_type` (prototype: often "Convertible Bonds" when detected)
- `sector` (when derived from section headers)
- `shares` (currently `null` in the Hartford convertible bonds example)
- `principal`
- `market_value`

This is **not** a complete production parser but a proof-of-concept aligned with the design document.


4. Extending the Prototype
--------------------------

To extend toward GSAM or BlackRock:

- Add new layout-specific extractor modules (e.g., `gsam_extractor.py`, `blackrock_extractor.py`).
- Introduce config-driven layout profiles (YAML/JSON) and a selector that chooses the right profile based on fund name/text.
- Generalize the CLI in `main.py` to:
  - Auto-detect the fund/layout.
  - Or accept a `--profile` argument.

These changes would follow the architecture in `system_design.md`.


