from __future__ import annotations

"""
CLI entrypoint for the prototype extractor.

The heavy lifting lives inside the `fund_extractor` package; this module wires
argument parsing, PDF loading, layout detection, and serialization together.
"""

import argparse
import json
import re
from pathlib import Path
from typing import List, Tuple

import pandas as pd

from fund_extractor.ai_fallbacks import ai_extract_holdings_from_pdf, ai_ocr_extract_pdf
from fund_extractor.generic_extractor import extract_with_layout
from fund_extractor.ingest import load_pdf
from fund_extractor.layout_config import LayoutConfig, detect_config_for_pdf, load_layout_configs
from fund_extractor.models import Holding


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Prototype: extract Schedule of Investments holdings from sample mutual fund PDFs."
    )
    parser.add_argument("pdf", help="Path or URL to the PDF report")
    parser.add_argument(
        "--fund-id",
        help="Optional layout config id to force (e.g. 'blackrock_international'). "
        "If omitted, the tool will auto-detect based on fund name.",
    )
    parser.add_argument("--out-json", type=Path, help="Optional explicit output JSON file path")
    parser.add_argument("--out-csv", type=Path, help="Optional explicit output CSV file path")
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print verbose diagnostics (selected pages, layout config, etc.) during extraction.",
    )
    return parser.parse_args()


def _ensure_text_or_fail(pdf, source_label: str) -> None:
    """
    Ensure that `pdf` has extractable text on at least one of the first few
    pages; otherwise, explain that OCR is not yet wired and exit.
    """
    has_text = False
    max_pages_to_check = min(5, len(pdf.pages))
    for idx in range(max_pages_to_check):
        page_text = (pdf.pages[idx].extract_text() or "").strip()
        if page_text:
            has_text = True
            break

    if not has_text:
        print(
            "No extractable text found on the first pages; PDF may be image-based.\n"
            "Attempting OCR fallback via ai_ocr_extract_pdf (currently a stub)."
        )
        _ = ai_ocr_extract_pdf(source_label, pages=range(len(pdf.pages)))
        raise SystemExit(
            "PDF appears to be image-based and OCR fallback is not yet implemented. "
            "Once ai_ocr_extract_pdf is wired to a real OCR engine, this path will "
            "feed OCR text into the extractor."
        )


def _detect_layout(pdf, args) -> Tuple[LayoutConfig, str, str, str]:
    """
    Detect the appropriate layout configuration and associated metadata.

    Returns (cfg, fund_name, report_date, date_tag).
    """
    config_dir = Path("configs")
    configs = load_layout_configs(config_dir)

    text_first_pages = "\n".join(page.extract_text() or "" for page in pdf.pages[:3])

    if args.fund_id:
        cfg = next((c for c in configs if c.id == args.fund_id), None)
        if cfg is None:
            raise SystemExit(f"No configuration found for fund id '{args.fund_id}'.")
    else:
        cfg = detect_config_for_pdf(text_first_pages, configs)
        if cfg is None:
            raise SystemExit("Unable to detect fund layout: no matching configuration found.")

    fund_name = cfg.id
    raw_date = ""
    date_tag = "unknown-date"

    # Accept both 'August 31, 2025' and compact 'AUGUST31,2025' styles.
    date_match = re.search(
        r"(January|February|March|April|May|June|July|August|September|October|November|December)\s*(\d{1,2}),\s*(\d{4})",
        text_first_pages,
        re.IGNORECASE,
    )
    if date_match:
        month, day, year = date_match.groups()
        raw_date = f"{month.title()} {int(day)}, {year}"
        # Build YYYYMMDD tag
        month_map = {
            "January": "01",
            "February": "02",
            "March": "03",
            "April": "04",
            "May": "05",
            "June": "06",
            "July": "07",
            "August": "08",
            "September": "09",
            "October": "10",
            "November": "11",
            "December": "12",
        }
        mm = month_map.get(month.title(), "00")
        date_tag = f"{year}{mm}{int(day):02d}"

    report_date = raw_date
    return cfg, fund_name, report_date, date_tag


def _prepare_output_paths(args, layout_id: str, date_tag: str) -> Tuple[Path, Path]:
    """
    Determine where JSON and CSV outputs should be written, creating parent
    directories as needed.
    """
    out_dir = Path("output")
    out_dir.mkdir(parents=True, exist_ok=True)

    stem = Path(args.pdf).stem
    out_json = args.out_json
    out_csv = args.out_csv

    if out_json is None:
        out_json = out_dir / f"{layout_id}_{date_tag}_{stem}.json"
    else:
        out_json.parent.mkdir(parents=True, exist_ok=True)

    if out_csv is None:
        out_csv = out_dir / f"{layout_id}_{date_tag}_{stem}.csv"
    else:
        out_csv.parent.mkdir(parents=True, exist_ok=True)

    return out_json, out_csv


def _serialize_outputs(holdings: List[Holding], out_json: Path, out_csv: Path) -> None:
    """
    Serialize holdings to JSON and CSV side by side.
    """
    data = [h.__dict__ for h in holdings]
    out_json.write_text(json.dumps(data, indent=2))

    df = pd.DataFrame(data)
    df.to_csv(out_csv, index=False)


def main() -> None:
    args = _parse_args()

    pdf = load_pdf(args.pdf)
    _ensure_text_or_fail(pdf, source_label=args.pdf)

    cfg, fund_name, report_date, date_tag = _detect_layout(pdf, args)

    holdings = extract_with_layout(
        pdf,
        cfg,
        fund_name=fund_name,
        report_date=report_date,
        verbose=args.verbose,
    )

    if not holdings and args.verbose:
        # Placeholder: future AI-based direct extraction fallback.
        # The current implementation is a stub and always returns [].
        _ = ai_extract_holdings_from_pdf(
            args.pdf,
            fund_name=fund_name,
            report_date=report_date,
        )

    out_json, out_csv = _prepare_output_paths(args, cfg.id, date_tag)
    _serialize_outputs(holdings, out_json, out_csv)

    print(f"Extracted {len(holdings)} holdings for layout '{cfg.id}'")
    print(f"JSON written to: {out_json}")
    print(f"CSV written to: {out_csv}")


if __name__ == "__main__":
    main()


