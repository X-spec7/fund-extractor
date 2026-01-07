import argparse
import json
import re
from pathlib import Path

import pandas as pd

from fund_extractor.ai_fallbacks import ai_extract_holdings_from_pdf, ai_ocr_extract_pdf
from fund_extractor.generic_extractor import extract_with_layout
from fund_extractor.ingest import load_pdf
from fund_extractor.layout_config import detect_config_for_pdf, load_layout_configs


def main() -> None:
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
    args = parser.parse_args()

    pdf = load_pdf(args.pdf)

    # If pdfplumber cannot see any text on the first few pages, assume this is
    # an image-based PDF and route through the OCR fallback (currently a stub).
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
        _ocr_text_by_page = ai_ocr_extract_pdf(args.pdf, pages=range(len(pdf.pages)))
        # For now we do not yet have an OCR-backed parser, so fail fast with a
        # clear message. In a future iteration, this OCR text would be passed
        # into a dedicated extraction path.
        raise SystemExit(
            "PDF appears to be image-based and OCR fallback is not yet implemented. "
            "Once ai_ocr_extract_pdf is wired to a real OCR engine, this path will "
            "feed OCR text into the extractor."
        )

    # Load configs and detect fund layout
    config_dir = Path("configs")
    configs = load_layout_configs(config_dir)

    text_first_pages = "\n".join(page.extract_text() or "" for page in pdf.pages[:3])

    cfg = None
    if args.fund_id:
        # Find config with matching id
        for c in configs:
            if c.id == args.fund_id:
                cfg = c
                break
        if cfg is None:
            raise SystemExit(f"No configuration found for fund id '{args.fund_id}'.")
    else:
        cfg = detect_config_for_pdf(text_first_pages, configs)
        if cfg is None:
            raise SystemExit("Unable to detect fund layout: no matching configuration found.")

    # Derive fund_name and report_date from text (best-effort)
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

    # Compute default output paths if not provided
    out_dir = Path("output")
    out_dir.mkdir(parents=True, exist_ok=True)

    stem = Path(args.pdf).stem
    if args.out_json is None:
        args.out_json = out_dir / f"{cfg.id}_{date_tag}_{stem}.json"
    else:
        args.out_json.parent.mkdir(parents=True, exist_ok=True)

    if args.out_csv is None:
        args.out_csv = out_dir / f"{cfg.id}_{date_tag}_{stem}.csv"
    else:
        args.out_csv.parent.mkdir(parents=True, exist_ok=True)

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
        _ai_holdings = ai_extract_holdings_from_pdf(
            args.pdf,
            fund_name=fund_name,
            report_date=report_date,
        )

    data = [h.__dict__ for h in holdings]
    args.out_json.write_text(json.dumps(data, indent=2))

    df = pd.DataFrame(data)
    df.to_csv(args.out_csv, index=False)

    print(f"Extracted {len(holdings)} holdings for layout '{cfg.id}'")
    print(f"JSON written to: {args.out_json}")
    print(f"CSV written to: {args.out_csv}")


if __name__ == "__main__":
    main()


