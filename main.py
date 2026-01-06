import argparse
import json
from pathlib import Path

import pandas as pd

from fund_extractor.ingest import load_pdf
from fund_extractor.hartford_extractor import extract_hartford_holdings


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Prototype: extract Schedule of Investments holdings from Hartford Balanced Income Fund PDF."
    )
    parser.add_argument("pdf", help="Path or URL to the Hartford PDF report")
    parser.add_argument(
        "--out-json", type=Path, default=Path("./output/hartford_holdings.json"), help="Output JSON file path"
    )
    parser.add_argument(
        "--out-csv", type=Path, default=Path("./output/hartford_holdings.csv"), help="Output CSV file path"
    )
    args = parser.parse_args()

    # Ensure output directory exists
    args.out_json.parent.mkdir(parents=True, exist_ok=True)
    args.out_csv.parent.mkdir(parents=True, exist_ok=True)

    pdf = load_pdf(args.pdf)
    holdings = extract_hartford_holdings(pdf)

    data = [h.__dict__ for h in holdings]
    args.out_json.write_text(json.dumps(data, indent=2))

    df = pd.DataFrame(data)
    df.to_csv(args.out_csv, index=False)

    print(f"Extracted {len(holdings)} holdings")
    print(f"JSON written to: {args.out_json}")
    print(f"CSV written to: {args.out_csv}")


if __name__ == "__main__":
    main()


