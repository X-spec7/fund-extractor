import argparse
import json
from pathlib import Path

import pandas as pd

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
    parser.add_argument(
        "--out-json", type=Path, default=Path("./output/holdings.json"), help="Output JSON file path"
    )
    parser.add_argument(
        "--out-csv", type=Path, default=Path("./output/holdings.csv"), help="Output CSV file path"
    )
    args = parser.parse_args()

    # Ensure output directory exists
    args.out_json.parent.mkdir(parents=True, exist_ok=True)
    args.out_csv.parent.mkdir(parents=True, exist_ok=True)

    pdf = load_pdf(args.pdf)

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

    # For this prototype, we derive fund_name and report_date very simply:
    fund_name = cfg.id
    report_date = ""

    holdings = extract_with_layout(pdf, cfg, fund_name=fund_name, report_date=report_date)

    data = [h.__dict__ for h in holdings]
    args.out_json.write_text(json.dumps(data, indent=2))

    df = pd.DataFrame(data)
    df.to_csv(args.out_csv, index=False)

    print(f"Extracted {len(holdings)} holdings for layout '{cfg.id}'")
    print(f"JSON written to: {args.out_json}")
    print(f"CSV written to: {args.out_csv}")


if __name__ == "__main__":
    main()


