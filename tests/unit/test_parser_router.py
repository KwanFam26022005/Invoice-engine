"""Unit tests for profile-aware parser router and fallback policy."""

import unicodedata
from pathlib import Path
import fitz
import pytest

from document_engine.core.models import PDFProfileType
from document_engine.intake.inspector import PDFInspector
from document_engine.routing.parser_router import ParserRouter


def create_sample_native_pdf(path: Path) -> Path:
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    page.insert_text((50, 50), "HOA DON GIA TRI GIA TANG\nMa so thue: 010999888\nSo tien: 5.000.000 VND")
    doc.save(path)
    doc.close()
    return path


def test_route_native_pdf_to_pymupdf(tmp_path: Path):
    pdf_path = create_sample_native_pdf(tmp_path / "invoice.pdf")
    inspector = PDFInspector()
    source_doc, profile = inspector.inspect(pdf_path)

    router = ParserRouter()
    outcome = router.route_and_parse(source_doc, profile)

    assert outcome.routing_decision.selected_parser == "pymupdf_native"
    assert outcome.selected_result.success is True
    assert outcome.selected_result.document_ir is not None
    norm_text = unicodedata.normalize("NFC", outcome.selected_result.document_ir.full_text)
    assert "HOA DON GIA TRI GIA TANG" in norm_text
    assert outcome.fallback_result is None


def test_fallback_trigger_on_empty_primary_output(tmp_path: Path):
    # Create empty PDF
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    doc.save(tmp_path / "empty.pdf")
    doc.close()

    inspector = PDFInspector()
    source_doc, profile = inspector.inspect(tmp_path / "empty.pdf")

    router = ParserRouter()
    outcome = router.route_and_parse(source_doc, profile, enable_fallback=True)

    assert outcome.routing_decision.attempt_number == 2
    assert outcome.routing_decision.fallback_trigger is not None
    assert outcome.fallback_result is not None
