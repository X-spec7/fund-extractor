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


def _contains_normalized(haystack: str, needle: str) -> bool:
    """
    Return True if 'needle' is found in 'haystack', ignoring whitespace
    differences and case. This helps when headers are broken by newlines
    or multiple spaces (e.g. 'Schedule of\\nInvestments').
    """
    if not haystack or not needle:
        return False
    h = re.sub(r"\s+", "", haystack).lower()
    n = re.sub(r"\s+", "", needle).lower()
    return n in h


def _guess_fund_name(text: str, default: str) -> str:
    """
    Best-effort extraction of fund name from page text.
    For GSAM/BlackRock-style reports, the fund name usually appears
    as a single line ending with 'Fund'.
    """
    if not text:
        return default
    m = re.search(r"(?im)^(.*Fund)\s*$", text)
    if m:
        return m.group(1).strip()
    return default


def extract_with_layout(
    pdf: pdfplumber.PDF, cfg: LayoutConfig, fund_name: str, report_date: str, verbose: bool = False
) -> List[Holding]:
    if cfg.layout_type == "hartford_custom":
        return extract_hartford_holdings(pdf)

    holdings: List[Holding] = []

    # Find anchor pages that clearly belong to a Schedule of Investments
    # for this layout. We use only the schedule header here so that a
    # single layout config can cover multiple funds in the same PDF
    # (e.g. multiple GSAM funds sharing the same table format).
    anchor_pages: List[int] = []
    for idx, page in enumerate(pdf.pages):
        text = page.extract_text() or ""
        if _contains_normalized(text, cfg.schedule_header):
            anchor_pages.append(idx)

    if verbose:
        print(f"[layout:{cfg.id}] anchor pages with header+fund match: {sorted(anchor_pages)}")

    # If no anchors found, fall back to simple header-based detection
    if not anchor_pages:
        schedule_pages: List[int] = []
        for idx, page in enumerate(pdf.pages):
            text = page.extract_text() or ""
            if _contains_normalized(text, cfg.schedule_header):
                schedule_pages.append(idx)
        if verbose:
            print(f"[layout:{cfg.id}] no anchors found; schedule pages (header only): {schedule_pages}")
    else:
        # Start with anchor pages, then examine the full contiguous range
        # between the first and last anchor page and include any pages that
        # look like they contain holdings.
        schedule_pages_set = set(anchor_pages)

        def page_looks_like_holdings(text: str) -> bool:
            if not text.strip():
                return False
            text_nospace_local = re.sub(r"\s+", "", text)
            # Instrument headers present?
            for hdr in (cfg.instrument_headers or {}).keys():
                hdr_nospace = re.sub(r"\s+", "", hdr)
                if hdr in text or hdr_nospace in text_nospace_local:
                    return True
            # Heuristic: several lines starting with shares and ending with a number
            count = 0
            for line in text.splitlines():
                line = line.strip()
                if re.match(r"^[0-9][0-9,]*\s+.*[0-9][0-9,]+$", line):
                    count += 1
                if count >= 3:
                    return True
            return False

        anchors_sorted = sorted(anchor_pages)
        range_start = anchors_sorted[0]
        range_end = anchors_sorted[-1]

        for idx in range(range_start, range_end + 1):
            if idx in schedule_pages_set:
                continue
            text = pdf.pages[idx].extract_text() or ""
            if page_looks_like_holdings(text):
                schedule_pages_set.add(idx)

        schedule_pages = sorted(schedule_pages_set)

        if verbose:
            print(f"[layout:{cfg.id}] final schedule page range {range_start}-{range_end}: {schedule_pages}")

    current_security_type: str | None = None

    if verbose:
        print(f"[layout:{cfg.id}] parsing pages: {schedule_pages}")

    for page_idx in schedule_pages:
        page = pdf.pages[page_idx]
        page_text = page.extract_text() or ""
        page_fund_name = _guess_fund_name(page_text, fund_name)
        width = page.width
        height = page.height

        # Compute column boxes generically based on the configured column count.
        # This supports 1, 2, 3, 4, ... columns laid out horizontally.
        if cfg.columns <= 1:
            boxes = [(0, 0, width, height)]
        else:
            col_width = width / float(cfg.columns)
            boxes = []
            for i in range(cfg.columns):
                x0 = col_width * i
                x1 = col_width * (i + 1)
                boxes.append((x0, 0, x1, height))

        for (x0, y0, x1, y1) in boxes:
            col_page = page.crop((x0, y0, x1, y1))
            text = col_page.extract_text() or ""

            current_country_iso3: str | None = None

            # Special handling for GSAM-like layouts where each holding spans
            # multiple lines: first line starts with shares, subsequent lines
            # contain description and eventually the value.
            if cfg.layout_type == "two_column_multiline_shares_first":
                pending_name_parts: List[str] = []
                pending_shares: float | None = None
                pending_value: float | None = None
                pending_country_iso3: str | None = None

                TRIM_PATTERNS = [
                    "( Cost",
                    "Cost$",
                    "Shares Dividend Rate",
                    "Investment Company",
                ]

                def finalize_pending():
                    if pending_shares is None or pending_value is None or not pending_name_parts:
                        return None
                    name = _normalize_name(" ".join(pending_name_parts))
                    for pat in TRIM_PATTERNS:
                        idx = name.find(pat)
                        if idx != -1:
                            name = name[:idx].rstrip()
                    # Skip entries that are purely numeric/percentage with no letters
                    if not re.search(r"[A-Za-z]", name):
                        return None
                    if not name:
                        return None
                    holdings.append(
                        Holding(
                            fund_name=page_fund_name,
                            report_date=report_date,
                            security_name=name,
                            security_type=current_security_type,
                            country_iso3=pending_country_iso3,
                            sector=None,
                            shares=pending_shares,
                            principal=None,
                            market_value=pending_value,
                        )
                    )
                    return True

                for raw_line in text.splitlines():
                    line = raw_line.strip()
                    if not line:
                        continue

                    line_nospace = re.sub(r"\s+", "", line)

                    # Explicitly skip Investment Company section headers on this page
                    if "Investment Company" in line or "Shares Dividend Rate" in line:
                        # Finalize any pending holding and stop processing this column
                        finalize_pending()
                        break

                    # Stop when a stop prefix or substring is encountered: finalize
                    # current holding, then stop processing this column/page.
                    stop = False
                    for p in cfg.stop_line_prefixes or []:
                        p_nospace = re.sub(r"\s+", "", p)
                        if line.startswith(p) or line_nospace.startswith(p_nospace):
                            stop = True
                            break
                    if stop or any(s in line for s in (cfg.stop_line_contains or [])):
                        finalize_pending()
                        break

                    # Instrument headers
                    for prefix, sec_type in (cfg.instrument_headers or {}).items():
                        if line.startswith(prefix):
                            current_security_type = sec_type
                            break

                    # Country headings (e.g. 'China–28.8%')
                    iso = country_heading_to_iso3(line)
                    if iso:
                        current_country_iso3 = iso
                        continue

                    # Skip noise lines
                    skip = False
                    for p in cfg.noise_prefixes or []:
                        p_nospace = re.sub(r"\s+", "", p)
                        if line.startswith(p) or line_nospace.startswith(p_nospace):
                            skip = True
                            break
                    if skip:
                        continue

                    if not re.search(r"[A-Za-z0-9]", line):
                        continue

                    # Start of a new holding: line begins with shares
                    m = re.match(r"^([0-9][0-9,]*)\s+(.*)$", line)
                    if m:
                        # Finalize previous pending holding
                        finalize_pending()
                        pending_name_parts = []
                        pending_value = None
                        pending_country_iso3 = current_country_iso3
                        pending_shares = _parse_number(m.group(1))
                        remainder = m.group(2)

                        # Any numeric token at end of this line is likely value if present
                        numeric_tokens = _parse_numeric_tokens(remainder)
                        if numeric_tokens:
                            # Use last numeric as value and strip it from text
                            val_pos, val_token = numeric_tokens[-1]
                            pending_value = _parse_number(val_token)
                            desc = remainder[:val_pos].rstrip("$ ").strip()
                        else:
                            desc = remainder

                        if desc:
                            pending_name_parts.append(desc)
                        continue

                    # Continuation line for current holding
                    if pending_shares is None:
                        continue

                    numeric_tokens = _parse_numeric_tokens(line)
                    desc = line
                    if numeric_tokens:
                        val_pos, val_token = numeric_tokens[-1]
                        pending_value = _parse_number(val_token)
                        desc = line[:val_pos].rstrip("$ ").strip()

                    if desc:
                        pending_name_parts.append(desc)

                # End of column: finalize any pending holding
                finalize_pending()

            else:
                for raw_line in text.splitlines():
                    line = raw_line.strip()
                    if not line:
                        continue

                    line_nospace = re.sub(r"\s+", "", line)

                    # Stop when a stop prefix or substring is encountered on this page
                    stop_page = False
                    for p in cfg.stop_line_prefixes or []:
                        p_nospace = re.sub(r"\s+", "", p)
                        if line.startswith(p) or line_nospace.startswith(p_nospace):
                            stop_page = True
                            break
                    if stop_page or any(s in line for s in (cfg.stop_line_contains or [])):
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
                    skip = False
                    for p in cfg.noise_prefixes or []:
                        p_nospace = re.sub(r"\s+", "", p)
                        if line.startswith(p) or line_nospace.startswith(p_nospace):
                            skip = True
                            break
                    if skip:
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
                            fund_name=page_fund_name,
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


