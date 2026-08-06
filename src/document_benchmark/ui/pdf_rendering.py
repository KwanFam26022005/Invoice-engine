"""PDF page rendering utilities for Streamlit local preview."""

from __future__ import annotations

import base64
from pathlib import Path


def render_pdf_page_to_png_bytes(pdf_path: Path, page_number: int = 1, dpi: int = 150) -> bytes | None:
    """Render a single page of a PDF file to PNG bytes in memory using PyMuPDF (fitz)."""
    if not pdf_path.exists():
        return None
    try:
        import fitz  # PyMuPDF

        doc = fitz.open(str(pdf_path))
        if page_number < 1 or page_number > len(doc):
            return None
        page = doc.load_page(page_number - 1)
        pix = page.get_pixmap(dpi=dpi)
        return pix.tobytes("png")
    except Exception:
        return None


def get_pdf_base64_data_uri(pdf_path: Path) -> str | None:
    """Read a local PDF file and convert to Base64 data URI for iframe embedding."""
    if not pdf_path.exists():
        return None
    try:
        raw_bytes = pdf_path.read_bytes()
        # Verify PDF magic bytes '%PDF'
        if not raw_bytes.startswith(b"%PDF"):
            return None
        b64_str = base64.b64encode(raw_bytes).decode("utf-8")
        return f"data:application/pdf;base64,{b64_str}"
    except Exception:
        return None
