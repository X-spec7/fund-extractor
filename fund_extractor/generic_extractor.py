import re
from pathlib import Path
from typing import List

import pdfplumber

from .country_codes import country_heading_to_iso3
from .hartford_extractor import extract_hartford_holdings
from .layout_config import LayoutConfig
from .models import Holding


def _parse_numeric_tokens(line: str) -> List[tuple[int, str]]:
    tokens: List[tuple[int, str]] = []
    for m in re.finditer(r"[0-9][0-9,]*", line):
        tokens.append((m.start(), m.group(0)))
    return tokens


def _parse_number(raw: str) -> float | None:
    cleaned = raw.replace(",", "").replace("$", "").strip()
    cleaned = re.sub(r"\*+|\u2020|\u2021", "", cleaned)
    if not cleaned or cleaned in ("-", "—"):
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def _normalize_name(name: str) -> str:
    # Insert spaces before capital letters when preceded by a non-space, non-capital
    name = re.sub(r"(?<=[^\sA-Z,])(?=[A-Z])", " ", name)
    # Space after comma
    name = re.sub(r",(?=[A-Za-z])", ", ", name)
    # Collapse multiple spaces
    name = re.sub(r"\s{2,}", " ", name)
    return name.strip()


def extract_with_layout(pdf: pdfplumber.PDF, cfg: LayoutConfig, fund_name: str, report_date: str) -> List[Holding]:
    if cfg.layout_type == "hartford_custom":
        return extract_hartford_holdings(pdf)

    holdings: List[Holding] = []

    # Find pages containing the Schedule of Investments header
    schedule_pages: List[int] = []
    for idx, page in enumerate(pdf.pages):
        text = page.extract_text() or ""
        if cfg.schedule_header in text:
            schedule_pages.append(idx)

    current_security_type: str | None = None
    end_reached = False

    for page_idx in schedule_pages:
        if end_reached:
            break

        page = pdf.pages[page_idx]
        width = page.width
        height = page.height

        if cfg.layout_type == "two_column_line_numeric" and cfg.columns == 2:
            boxes = [
                (0, 0, width / 2.0, height),
                (width / 2.0, 0, width, height),
            ]
        else:
            boxes = [(0, 0, width, height)]

        for (x0, y0, x1, y1) in boxes:
            if end_reached:
                break

            col_page = page.crop((x0, y0, x1, y1))
            text = col_page.extract_text() or ""

            current_country_iso3: str | None = None

            for raw_line in text.splitlines():
                line = raw_line.strip()
                if not line:
                    continue

                # Stop when a stop prefix or substring is encountered
                if any(line.startswith(p) for p in cfg.stop_line_prefixes or []):
                    end_reached = True
                    break
                if any(s in line for s in cfg.stop_line_contains or []):
                    end_reached = True
                    break

                # Instrument headers
                for prefix, sec_type in (cfg.instrument_headers or {}).items():
                    if line.startswith(prefix):
                        current_security_type = sec_type
                        break

                # Country headings (e.g. 'Canada—6.5%')
                iso = country_heading_to_iso3(line)
                if iso:
                    current_country_iso3 = iso
                    continue

                # Skip noise lines
                if any(line.startswith(p) for p in cfg.noise_prefixes or []):
                    continue

                if not re.search(r"[A-Za-z]", line):
                    continue

                numeric_tokens = _parse_numeric_tokens(line)
                if len(numeric_tokens) <= max(cfg.shares_token_index, cfg.value_token_index):
                    continue

                shares_idx, shares_token = numeric_tokens[cfg.shares_token_index]
                _, value_token = numeric_tokens[cfg.value_token_index]

                shares = _parse_number(shares_token)
                market_value = _parse_number(value_token)

                name_end = shares_idx
                security_name = line[:name_end].rstrip(". ").strip()
                security_name = _normalize_name(security_name)
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


