import re
from typing import List, Optional

import pdfplumber

from .country_codes import country_heading_to_iso3
from .models import Holding


BLACKROCK_FUND_NAME_PATTERN = re.compile(r"BlackRock\s*International\s*Fund", re.IGNORECASE)
BLACKROCK_DATE_PATTERN = re.compile(
    r"(January|February|March|April|May|June|July|August|September|October|November|December)\s*\.?\s*\d{1,2},\s*\d{4}",
    re.IGNORECASE,
)


def _extract_fund_name_and_date(pdf: pdfplumber.PDF) -> tuple[str, str]:
    text = pdf.pages[0].extract_text() or ""
    # Some PDFs remove spaces, so search on a whitespace-stripped version.
    fund_match = BLACKROCK_FUND_NAME_PATTERN.search(text.replace(" ", ""))
    date_match = BLACKROCK_DATE_PATTERN.search(text)

    fund_name = "BlackRock International Fund"
    if fund_match:
        fund_name = "BlackRock International Fund"

    report_date = ""
    if date_match:
        raw = date_match.group(0).strip()
        # Normalize formats like 'AUGUST31,2025' to 'August 31, 2025'
        m = re.match(
            r"(January|February|March|April|May|June|July|August|September|October|November|December)\s*(\d{1,2}),\s*(\d{4})",
            raw,
            re.IGNORECASE,
        )
        if m:
            month, day, year = m.groups()
            report_date = f"{month.title()} {int(day)}, {year}"
        else:
            report_date = raw

    return fund_name, report_date


def _parse_numeric_tokens(line: str) -> List[tuple[int, str]]:
    """
    Return list of (start_index, token_text) for numeric tokens in a line.
    """
    tokens: List[tuple[int, str]] = []
    for m in re.finditer(r"[0-9][0-9,]*", line):
        tokens.append((m.start(), m.group(0)))
    return tokens


def _parse_number(raw: str) -> Optional[float]:
    cleaned = raw.replace(",", "").replace("$", "").strip()
    cleaned = re.sub(r"\*+|\u2020|\u2021", "", cleaned)
    if not cleaned or cleaned in ("-", "—"):
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def _normalize_security_name(name: str) -> str:
    """
    Heuristically re-insert spaces that are often missing in the PDF text, e.g.
    'AssaAbloyAB,ClassB' -> 'Assa Abloy AB, Class B'.
    """
    # Space between lowercase letter and uppercase letter
    name = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", name)
    # Space after comma if missing
    name = re.sub(r",(?=[A-Za-z])", ", ", name)
    # Collapse multiple spaces
    name = re.sub(r"\\s{2,}", " ", name)
    return name.strip()


def extract_blackrock_international(pdf: pdfplumber.PDF) -> List[Holding]:
    """
    Extract holdings from BlackRock International Fund Schedule of Investments.

    This implementation is line-based and tailored to the sample layout in blackrock.pdf.
    """
    fund_name, report_date = _extract_fund_name_and_date(pdf)
    holdings: List[Holding] = []

    # Identify pages that contain the Schedule of Investments
    schedule_pages: List[int] = []
    for idx, page in enumerate(pdf.pages):
        text = page.extract_text() or ""
        if "Schedule of Investments" in text:
            schedule_pages.append(idx)

    current_country_heading: Optional[str] = None
    current_country_iso3: Optional[str] = None
    current_security_type: Optional[str] = None

    for page_idx in schedule_pages:
        text = pdf.pages[page_idx].extract_text() or ""
        for raw_line in text.splitlines():
            line = raw_line.strip()
            if not line:
                continue

            # Detect section headers (but do not skip line; it may also carry a country heading)
            if line.startswith("CommonStocks"):
                current_security_type = "Common Stock"
            if line.startswith("MoneyMarketFunds"):
                current_security_type = "Money Market Fund"
            # Country headings like 'Canada—6.5%' or 'Sweden—5.2%'
            iso = country_heading_to_iso3(line)
            if iso:
                current_country_heading = line
                current_country_iso3 = iso
                continue

            # Skip header and total lines
            if line.startswith("Security Shares Value") or line.startswith("Total"):
                continue

            # We only care about lines with letters and at least two numeric tokens
            if not re.search(r"[A-Za-z]", line):
                continue

            numeric_tokens = _parse_numeric_tokens(line)
            if len(numeric_tokens) < 2:
                continue

            # Use first numeric token as shares, second as market value; ignore any trailing totals.
            first_idx, first_token = numeric_tokens[0]
            _, second_token = numeric_tokens[1]

            shares = _parse_number(first_token)
            market_value = _parse_number(second_token)

            security_name = line[:first_idx].rstrip(". ").strip()
            security_name = _normalize_security_name(security_name)
            if not security_name:
                continue

            holdings.append(
                Holding(
                    fund_name=fund_name,
                    report_date=report_date,
                    security_name=security_name,
                    security_type=current_security_type,
                    country_iso3=current_country_iso3,
                    sector=None,
                    shares=shares,
                    principal=None,
                    market_value=market_value,
                )
            )

    return holdings


