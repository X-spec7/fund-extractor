from __future__ import annotations

"""
Boilerplate placeholders for AI-based fallbacks (LLM extraction, OCR, etc.).

These functions are intentionally implemented as no-ops / mocks so that the
core pipeline remains fully deterministic and offline. They define the
expected interfaces for future AI integrations without actually calling
external services.
"""

from pathlib import Path
from typing import Dict, Iterable, List, Optional, Union

from .models import Holding


SourcePath = Union[str, Path]


def ai_ocr_extract_pdf(
    source: SourcePath,
    pages: Optional[Iterable[int]] = None,
) -> Dict[int, str]:
    """
    Mock OCR fallback.

    Intended future behavior:
      - Run a cheap on-prem OCR (e.g. Tesseract) on the specified pages.
      - Optionally fall back to a hosted AI OCR service for very hard cases.
      - Return a mapping of page index -> extracted text.

    Current behavior:
      - Does not perform any OCR.
      - Returns an empty mapping as a placeholder.
    """
    # NOTE: this is deliberately a no-op stub.
    return {}


def ai_extract_holdings_from_pdf(
    source: SourcePath,
    fund_name: str,
    report_date: str,
) -> List[Holding]:
    """
    Mock end-to-end AI extraction fallback.

    Intended future behavior:
      - When config-based parsing fails (e.g. zero holdings extracted),
        call an LLM on a small set of representative pages to extract
        structured holding items directly.

    Current behavior:
      - Does not call any AI service.
      - Always returns an empty list, leaving the caller's result unchanged.
    """
    # NOTE: this is deliberately a no-op stub.
    return []



