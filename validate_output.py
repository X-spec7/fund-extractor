import argparse
import json
import math
from pathlib import Path
from typing import List

import pandas as pd

from fund_extractor.models import Holding
from fund_extractor.validator import validate_holdings


def _to_optional_float(value):
    if value is None:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    if isinstance(value, str):
        s = value.strip()
        if not s:
            return None
        try:
            return float(s.replace(",", ""))
        except ValueError:
            return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _to_optional_str(value):
    if value is None:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    s = str(value).strip()
    return s or None


def _load_holdings_from_json(path: Path) -> List[Holding]:
    raw = json.loads(path.read_text())
    if not isinstance(raw, list):
        raise ValueError("JSON file must contain a list of holding objects.")

    holdings: List[Holding] = []
    for idx, item in enumerate(raw):
        if not isinstance(item, dict):
            raise ValueError(f"JSON element at index {idx} is not an object.")
        holdings.append(
            Holding(
                fund_name=item.get("fund_name", "") or "",
                report_date=item.get("report_date", "") or "",
                security_name=item.get("security_name", "") or "",
                security_type=_to_optional_str(item.get("security_type")),
                country_iso3=_to_optional_str(item.get("country_iso3")),
                sector=_to_optional_str(item.get("sector")),
                shares=_to_optional_float(item.get("shares")),
                principal=_to_optional_float(item.get("principal")),
                market_value=_to_optional_float(item.get("market_value")),
            )
        )
    return holdings


def _load_holdings_from_csv(path: Path) -> List[Holding]:
    df = pd.read_csv(path)
    holdings: List[Holding] = []
    for _, row in df.iterrows():
        # pandas Series.get provides a default when the column is missing
        holdings.append(
            Holding(
                fund_name=(row.get("fund_name") or ""),
                report_date=(row.get("report_date") or ""),
                security_name=(row.get("security_name") or ""),
                security_type=_to_optional_str(row.get("security_type")),
                country_iso3=_to_optional_str(row.get("country_iso3")),
                sector=_to_optional_str(row.get("sector")),
                shares=_to_optional_float(row.get("shares")),
                principal=_to_optional_float(row.get("principal")),
                market_value=_to_optional_float(row.get("market_value")),
            )
        )
    return holdings


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Validate extracted holdings JSON/CSV files."
    )
    parser.add_argument("file", type=Path, help="Path to JSON or CSV file to validate")
    parser.add_argument(
        "--format",
        choices=["json", "csv"],
        help="Input format (auto-detected from extension if omitted).",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit with non-zero status code if validation finds errors.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print detailed validation messages.",
    )
    args = parser.parse_args()

    if args.format:
        fmt = args.format
    else:
        suffix = args.file.suffix.lower()
        if suffix == ".json":
            fmt = "json"
        elif suffix == ".csv":
            fmt = "csv"
        else:
            raise SystemExit(
                "Could not infer format from extension; please pass --format json|csv."
            )

    if not args.file.exists():
        raise SystemExit(f"File not found: {args.file}")

    if fmt == "json":
        holdings = _load_holdings_from_json(args.file)
    else:
        holdings = _load_holdings_from_csv(args.file)

    result = validate_holdings(holdings)
    errors = result.get("errors", [])
    warnings = result.get("warnings", [])

    print(f"Validated {len(holdings)} holdings from {args.file}")
    print(f"Validation summary: {len(errors)} error(s), {len(warnings)} warning(s).")

    if args.verbose:
        for msg in errors:
            print(f"[VALIDATION][ERROR] {msg}")
        for msg in warnings:
            print(f"[VALIDATION][WARN] {msg}")

    if args.strict and errors:
        raise SystemExit(1)


if __name__ == "__main__":
    main()


