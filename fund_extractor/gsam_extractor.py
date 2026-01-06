import re
from typing import List, Optional

import pdfplumber

from .country_codes import country_heading_to_iso3
from .models import Holding


GSAM_FUND_TITLE = "GOLDMAN SACHS EMERGING MARKETS EQUITY FUND"
DATE_PATTERN = re.compile(
    r"(January|February|March|April|May|June|July|August|September|October|November|December)\\s*\\d{1,2},\\s*\\d{4}",
    re.IGNORECASE,
)


def _parse_numeric_tokens(line: str) -> List[tuple[int, str]]:
    tokens: List[tuple[int, str]] = []
    for m in re.finditer(r"[0-9][0-9,]*", line):
        tokens.append((m.start(), m.group(0)))
    return tokens


def _parse_number(raw: str) -> Optional[float]:
    cleaned = raw.replace(",", "").replace("$", "").strip()
    cleaned = re.sub(r"\\*+|\\u2020|\\u2021", "", cleaned)
    if not cleaned or cleaned in ("-", "—"):
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def extract_gsam_emerging_markets(pdf: pdfplumber.PDF) -> List[Holding]:
    """
    Extract holdings for the Goldman Sachs Emerging Markets Equity Fund
    from gsam.pdf, using the Schedule of Investments section.
    """
    holdings: List[Holding] = []

    start_page_idx: Optional[int] = None
    report_date = ""

    # Locate the first page for this fund's Schedule of Investments
    for idx, page in enumerate(pdf.pages):
        text = page.extract_text() or ""
        if GSAM_FUND_TITLE in text and "Schedule of Investments" in text:
            start_page_idx = idx
            date_match = DATE_PATTERN.search(text)
            if date_match:
                report_date = date_match.group(0).strip()
            break

    if start_page_idx is None:
        return holdings

    fund_name = "Goldman Sachs Emerging Markets Equity Fund"

    current_country_iso3: Optional[str] = None
    current_security_type: Optional[str] = None

    for page in pdf.pages[start_page_idx:]:
        text = page.extract_text() or ""
        # Stop when we reach the sector summary that follows the table
        if "%of" in text and "Market" in text and "SectorName" in text:
            break

        for raw_line in text.splitlines():
            line = raw_line.strip()
            if not line:
                continue

            # Detect instrument type headings
            if line.startswith("CommonStocks"):
                current_security_type = "Common Stock"
                continue
            if line.startswith("PreferredStock"):
                current_security_type = "Preferred Stock"
                continue

            # Detect country headings such as "Brazil–5.4%" or "China–28.8%"
            if "–" in line or "—" in line:
                iso = country_heading_to_iso3(line)
                if iso:
                    current_country_iso3 = iso
                    continue

            # Skip obvious headers and totals
            if line.startswith("Shares Description") or line.startswith("TOTAL") or line.startswith("TOTTTAL"):
                continue

            if not re.search(r"[A-Za-z]", line):
                continue

            numeric_tokens = _parse_numeric_tokens(line)
            if len(numeric_tokens) < 2:
                continue

            first_idx, first_token = numeric_tokens[0]
            _, last_token = numeric_tokens[-1]

            shares = _parse_number(first_token)
            market_value = _parse_number(last_token)

            security_name = line[:first_idx].strip()
            security_name = security_name.rstrip(".,*")
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


