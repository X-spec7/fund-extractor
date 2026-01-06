import re
from typing import List, Optional

import pdfplumber

from .hartford_profile import HartfordHolding, HARTFORD_SOI_HEADER_KEY


FUND_NAME_PATTERN = re.compile(r"The Hartford .* Fund", re.IGNORECASE)
REPORT_DATE_PATTERN = re.compile(
    r"(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},\s+\d{4}",
    re.IGNORECASE,
)


def _find_fund_name_and_date(pdf: pdfplumber.PDF) -> (str, str):
    text = "\n".join(page.extract_text() or "" for page in pdf.pages[:3])
    fund_match = FUND_NAME_PATTERN.search(text)
    date_match = REPORT_DATE_PATTERN.search(text)
    fund_name = fund_match.group(0).strip() if fund_match else ""
    report_date = date_match.group(0).strip() if date_match else ""
    return fund_name, report_date


def _find_schedule_start_page(pdf: pdfplumber.PDF) -> Optional[int]:
    for idx, page in enumerate(pdf.pages):
        text = page.extract_text() or ""
        if HARTFORD_SOI_HEADER_KEY.lower() in text.lower():
            return idx
    return None


def _parse_number(raw: str) -> Optional[float]:
    if not raw:
        return None
    cleaned = raw.replace(",", "").replace("$", "").strip()
    cleaned = re.sub(r"\*+|\u2020|\u2021", "", cleaned)  # remove footnote markers, daggers
    if cleaned in ("", "-", "—"):
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def extract_hartford_holdings(pdf: pdfplumber.PDF) -> List[HartfordHolding]:
    fund_name, report_date = _find_fund_name_and_date(pdf)
    start_page_idx = _find_schedule_start_page(pdf)
    if start_page_idx is None:
        return []

    holdings: List[HartfordHolding] = []
    current_sector: Optional[str] = None
    current_security_type: Optional[str] = None

    # For prototype: scan a limited number of pages after the Schedule start.
    for page in pdf.pages[start_page_idx : start_page_idx + 5]:
        text = page.extract_text() or ""
        # Simple heuristics to track sector and security type from headings
        for line in text.splitlines():
            lower = line.lower()
            if "convertible bonds" in lower:
                current_security_type = "Convertible Bonds"
            # Sector lines often look like "Airlines - 0.0%"
            if "-" in line and "%" in line:
                parts = line.split("-")[0].strip()
                if parts:
                    current_sector = parts

        tables = page.extract_tables()
        for table in tables:
            # Expect Hartford style: security name may appear in one row,
            # with principal/market value in numeric columns in adjacent row(s).
            for row in table:
                if not any(row):
                    continue
                # Heuristic: numeric-looking columns towards the right
                numeric_values = [_parse_number(cell or "") for cell in row]
                has_money = any(v is not None for v in numeric_values)
                if not has_money:
                    # treat this as a potential security name row
                    security_candidate = " ".join(c for c in row if c).strip()
                    # avoid pure headers and totals
                    if (
                        security_candidate
                        and "total" not in security_candidate.lower()
                        and HARTFORD_SOI_HEADER_KEY.lower() not in security_candidate.lower()
                    ):
                        last_name = security_candidate
                    continue

                # if we have numeric columns, pair them with last seen security name
                principal = None
                market_value = None
                if len(row) >= 2:
                    principal = _parse_number(row[0] or "")
                    market_value = _parse_number(row[1] or "")

                security_name = locals().get("last_name", "").strip()
                if not security_name:
                    continue

                holdings.append(
                    HartfordHolding(
                        fund_name=fund_name,
                        report_date=report_date,
                        security_name=security_name,
                        security_type=current_security_type,
                        sector=current_sector,
                        shares=None,  # for convertible bonds, treat numeric as principal
                        principal=principal,
                        market_value=market_value,
                    )
                )

    return holdings


