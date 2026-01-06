import argparse
import json
from pathlib import Path

import pandas as pd

from fund_extractor.blackrock_extractor import extract_blackrock_international
from fund_extractor.gsam_extractor import extract_gsam_emerging_markets
from fund_extractor.hartford_extractor import extract_hartford_holdings
from fund_extractor.ingest import load_pdf


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Prototype: extract Schedule of Investments holdings from sample mutual fund PDFs."
    )
    parser.add_argument("pdf", help="Path or URL to the PDF report")
    parser.add_argument(
        "--fund",
        choices=["hartford", "blackrock", "gsam-em"],
        default="hartford",
        help="Which sample fund layout to use for parsing.",
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

    if args.fund == "hartford":
        holdings = extract_hartford_holdings(pdf)
    elif args.fund == "blackrock":
        holdings = extract_blackrock_international(pdf)
    else:
        holdings = extract_gsam_emerging_markets(pdf)

    data = [h.__dict__ for h in holdings]
    args.out_json.write_text(json.dumps(data, indent=2))

    df = pd.DataFrame(data)
    df.to_csv(args.out_csv, index=False)

    print(f"Extracted {len(holdings)} holdings for fund profile '{args.fund}'")
    print(f"JSON written to: {args.out_json}")
    print(f"CSV written to: {args.out_csv}")


if __name__ == "__main__":
    main()


