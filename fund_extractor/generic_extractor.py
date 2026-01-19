from __future__ import annotations

"""
Generic, config-driven extraction of holdings from Schedule of Investments pages.

This module deliberately keeps the parsing logic layout-agnostic and delegates
all layout-specific details to `LayoutConfig`. Adding support for a new fund
family should usually only require a new YAML config, not code changes.
"""

import re
from typing import List, Tuple

import pdfplumber

from .country_codes import country_heading_to_iso3
from .layout_config import LayoutConfig
from .models import Holding


NumericToken = Tuple[int, str]


def _parse_numeric_tokens(line: str) -> List[NumericToken]:
    """
    Return a list of (start_index, token_text) numeric substrings found in `line`.

    Numeric tokens are contiguous runs of digits (optionally containing commas)
    that begin with a digit, e.g. '1,234'.
    """
    tokens: List[NumericToken] = []
    for m in re.finditer(r"[0-9][0-9,]*", line):
        tokens.append((m.start(), m.group(0)))
    return tokens


def _parse_number(raw: str) -> float | None:
    """
    Normalize and parse a numeric token into a float.

    Returns None for empty placeholders, dashes, or values that cannot be
    parsed as floats.
    """
    cleaned = raw.replace(",", "").replace("$", "").strip()
    cleaned = re.sub(r"\*+|\u2020|\u2021", "", cleaned)
    if not cleaned or cleaned in ("-", "—"):
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def _normalize_name(name: str) -> str:
    """
    Normalize security names:
    - Insert spaces between lower-case and upper-case transitions (AssaAbloy -> Assa Abloy)
    - Normalize spaces around commas, ampersands, and parentheses.
    """
    if not name:
        return ""

    # Space between lowercase (including accented) and uppercase letters
    name = re.sub(r"(?<=[a-zà-ÿ])(?=[A-Z])", " ", name)

    # Ensure a space after comma if missing
    name = re.sub(r",(?=\S)", ", ", name)

    # Normalize spaces around '&'
    name = re.sub(r"\s*&\s*", " & ", name)

    # Remove spaces right after '('
    name = re.sub(r"\(\s+", "(", name)

    # Ensure space before '(' when attached to a word (but not after a hyphen)
    name = re.sub(r"(?<=[A-Za-z])\(", " (", name)

    # Collapse multiple spaces and trim
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
    """
    Extract holdings from `pdf` using the provided layout configuration.

    The function detects schedule pages for the layout, walks each configured
    column, and parses line-level content into `Holding` objects.
    """
    holdings: List[Holding] = []

    schedule_pages = _detect_schedule_pages(pdf, cfg, verbose=verbose)

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

            # Special handling for GSAM-like layouts where each holding spans
            # multiple lines: first line starts with shares, subsequent lines
            # contain description and eventually the value.
            if cfg.layout_type == "two_column_multiline_shares_first":
                current_security_type = _extract_multiline_shares_first(
                    text=text,
                    cfg=cfg,
                    holdings=holdings,
                    page_fund_name=page_fund_name,
                    report_date=report_date,
                    current_security_type=current_security_type,
                )
            else:
                current_security_type = _extract_line_numeric_layout(
                    text=text,
                    cfg=cfg,
                    holdings=holdings,
                    page_fund_name=page_fund_name,
                    report_date=report_date,
                    current_security_type=current_security_type,
                )

    return holdings


def _detect_schedule_pages(pdf: pdfplumber.PDF, cfg: LayoutConfig, verbose: bool) -> List[int]:
    """
    Detect which pages in `pdf` belong to the Schedule of Investments for
    this layout.

    Strategy:
      - Find "anchor" pages that clearly contain the configured schedule header.
      - If no anchors exist, fall back to simple header-based detection.
      - Otherwise, examine all pages between the first and last anchor and
        include any that visually look like holdings pages (instrument headers
        present, or several numeric rows).
    """
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

    return schedule_pages


def _extract_multiline_shares_first(
    *,
    text: str,
    cfg: LayoutConfig,
    holdings: List[Holding],
    page_fund_name: str,
    report_date: str,
    current_security_type: str | None,
) -> str | None:
    """
    Extraction strategy for layouts where each holding can span multiple
    lines and the first line begins with the share count.
    """
    pending_name_parts: List[str] = []
    pending_shares: float | None = None
    pending_value: float | None = None
    pending_country_iso3: str | None = None
    current_country_iso3: str | None = None

    TRIM_PATTERNS = [
        "( Cost",
        "Cost$",
        "Shares Dividend Rate",
        "Investment Company",
    ]

    def finalize_pending() -> bool:
        nonlocal pending_name_parts, pending_shares, pending_value, pending_country_iso3
        if pending_shares is None or pending_value is None or not pending_name_parts:
            return False
        name = _normalize_name(" ".join(pending_name_parts))
        for pat in TRIM_PATTERNS:
            idx = name.find(pat)
            if idx != -1:
                name = name[:idx].rstrip()
        # Skip entries that are purely numeric/percentage with no letters
        if not re.search(r"[A-Za-z]", name):
            return False
        if not name:
            return False
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
    return current_security_type


def _extract_line_numeric_layout(
    *,
    text: str,
    cfg: LayoutConfig,
    holdings: List[Holding],
    page_fund_name: str,
    report_date: str,
    current_security_type: str | None,
) -> str | None:
    """
    Extraction strategy for layouts where each holding is represented on a
    single line that contains both the share amount and value as numeric
    tokens.
    """
    current_country_iso3: str | None = None

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

    return current_security_type



