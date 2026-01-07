Prototype: Mutual Fund PDF Schedule of Investments Extractor
============================================================

This **prototype** includes implementation of a configurable system
for extracting holdings data from mutual fund PDF reports (e.g., BlackRock and
GSAM funds) from their **Schedule of Investments** sections.


1. Setup
--------

Requirements:

- Python 3.10+ (recommended)

Install Python dependencies:

```bash
cd /root/test/fund-extractor
pip3 install -r requirements.txt
```

Create a `.env` file (or export an environment variable) with your OpenAI API key
if you plan to use the config generator:

```bash
echo "OPENAI_API_KEY=sk-..." >> .env
```


2. Running the Extractor
------------------------

The main entry point is `main.py`, which uses **layout configs** (YAML files in
`configs/`) plus a generic extractor to parse different fund PDFs.

Basic usage:

```bash
python main.py /path/to/report.pdf --fund-id <layout_id>
```

Examples (see `Makefile` for shortcuts):

```bash
# BlackRock International Fund sample
make run-blackrock

# GSAM Emerging Markets Equity and related GSAM funds
make run-gsam-em
```

By default, outputs are written to `output/` with filenames that include the
layout id, detected report date (when available), and source PDF stem, e.g.:

- `output/blackrock_international_20250831_blackrock.json`
- `output/gsam_emerging_markets_equity_20240430_gsam.csv`


3. Layout Configs
-----------------

Layout configurations live in `configs/` and are YAML files describing how to
parse a family of reports. Each config has (roughly) the following shape:

```yaml
id: blackrock_international
schedule_header: "Schedule of Investments"
layout:
  type: two_column_multiline_shares_first
  columns: 2
  shares_token_index: 0
  value_token_index: 1
instrument_headers:
  CommonStocks: "Common Stock"
stop_line_prefixes:
  - "Total Long-Term Investments"
stop_line_contains: []
noise_prefixes:
  - "(Cost:$"
  - "Other Assets"
  - "Net Assets"
```

The generic extractor (`fund_extractor/generic_extractor.py`) uses these
settings to:

- Find the Schedule of Investments pages.
- Split pages into columns.
- Merge multi-line rows.
- Map numeric tokens to `shares` and `market_value`.
- Stop at totals / summaries and skip noisy lines.

The output schema per holding (JSON/CSV) is:

- `fund_name`
- `report_date`
- `security_name`
- `security_type`
- `country_iso3`
- `sector`
- `shares`
- `principal`
- `market_value`


4. Generating New Layout Configs with AI
----------------------------------------

To onboard a new fund family quickly, you can use `generate_config.py` to
bootstrap a YAML config using an LLM, based on a small sample of pages from a
report in `report_samples/`.

Generate configs for all PDFs in `report_samples/`:

```bash
make gen-config
```

or for a single sample PDF:

```bash
python generate_config.py report_samples/blackrock.pdf --id blackrock_international
```

This will write YAML files into `generated_configs/`. You should review and, if
necessary, tweak these YAMLs before moving them into `configs/` for use in
production runs.


5. Notes
--------

- OCR support: currently the extractor relies on `pdfplumber` text extraction.
  For fully image-based PDFs, you can extend `generic_extractor` to call Tesseract
  (or another OCR tool) on pages where no text is found.
- The system is optimized to keep AI usage **low-cost**: LLMs are used only at
  **onboarding time** to suggest configs. All actual extraction/parsing at scale
  is deterministic Python code driven by those configs.

