import io
from pathlib import Path
from typing import Union

import pdfplumber
import requests


def load_pdf(source: Union[str, Path]):
    """
    Load a PDF from a local path or HTTP/HTTPS URL and return a pdfplumber.PDF object.
    """
    src = str(source)
    if src.startswith("http://") or src.startswith("https://"):
        resp = requests.get(src)
        resp.raise_for_status()
        content = resp.content
        # Basic guard: many fund landing pages are HTML, not direct PDFs.
        # Check for a PDF header or content-type to avoid confusing errors.
        content_type = resp.headers.get("Content-Type", "").lower()
        looks_like_pdf = content.startswith(b"%PDF") or "pdf" in content_type
        if not looks_like_pdf:
            raise ValueError(
                "URL does not appear to be a direct PDF. "
                "Please provide a direct PDF URL (ending in .pdf or with Content-Type application/pdf) "
                "or download the report and pass a local file path."
            )
        return pdfplumber.open(io.BytesIO(content))

    return pdfplumber.open(Path(src))


