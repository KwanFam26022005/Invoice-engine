"""Unit tests for profile-aware parser router and fallback policy using isolated fake parsers."""

import unicodedata
from pathlib import Path
import fitz

from document_engine.core.models import PDFProfileType
from document_engine.intake.inspector import PDFInspector
from document_engine.ir.models import (
    DocumentIR,
    DocumentParseResult,
    DocumentProfile,
    PageIR,
    ParseWarning,
    ParserProvenance,
    SourceDocument,
    generate_page_id,
)
from document_engine.parsers.base import DocumentParser, ParserHealth, ParserSpec
from document_engine.parsers.registry import ParserRegistry
from document_engine.routing.parser_router import ParserRouter


class FakeNativeParser(DocumentParser):
    @property
    def spec(self) -> ParserSpec:
        return ParserSpec(
            parser_id="pymupdf_native",
            name="Fake Native Parser",
            supported_profiles=[PDFProfileType.NATIVE_PDF],
        )

    def healthcheck(self) -> ParserHealth:
        return ParserHealth(parser_id=self.parser_id, healthy=True)

    def supports(self, profile: DocumentProfile) -> bool:
        return True

    def parse(self, document: SourceDocument, profile: DocumentProfile) -> DocumentParseResult:
        if "empty" in document.filename:
            doc_ir = DocumentIR(
                document_id=document.document_id,
                source_document=document,
                profile=profile,
                provenance=ParserProvenance(parser_id=self.parser_id, parser_version="1.0.0"),
                pages=[],
                full_text="",
            )
            return DocumentParseResult(success=True, document_ir=doc_ir)

        page_id = generate_page_id(document.document_id, 1)
        doc_ir = DocumentIR(
            document_id=document.document_id,
            source_document=document,
            profile=profile,
            provenance=ParserProvenance(parser_id=self.parser_id, parser_version="1.0.0"),
            pages=[
                PageIR(
                    page_id=page_id,
                    page_number=1,
                    width=595.0,
                    height=842.0,
                    text_content="HOA DON GIA TRI GIA TANG",
                )
            ],
            full_text="HOA DON GIA TRI GIA TANG",
        )
        return DocumentParseResult(success=True, document_ir=doc_ir)


class FakeFallbackParser(DocumentParser):
    @property
    def spec(self) -> ParserSpec:
        return ParserSpec(
            parser_id="paddleocr_vl",
            name="Fake Fallback Parser",
            supported_profiles=[PDFProfileType.NATIVE_PDF, PDFProfileType.SCAN_PDF],
            is_fallback=True,
        )

    def healthcheck(self) -> ParserHealth:
        return ParserHealth(parser_id=self.parser_id, healthy=True)

    def supports(self, profile: DocumentProfile) -> bool:
        return True

    def parse(self, document: SourceDocument, profile: DocumentProfile) -> DocumentParseResult:
        page_id = generate_page_id(document.document_id, 1)
        doc_ir = DocumentIR(
            document_id=document.document_id,
            source_document=document,
            profile=profile,
            provenance=ParserProvenance(parser_id=self.parser_id, parser_version="1.0.0"),
            pages=[
                PageIR(
                    page_id=page_id,
                    page_number=1,
                    width=595.0,
                    height=842.0,
                    text_content="Fake Fallback Extracted Content",
                )
            ],
            full_text="Fake Fallback Extracted Content",
            warnings=[ParseWarning(code="FALLBACK_USED", message="Fallback executed")],
        )
        return DocumentParseResult(success=True, document_ir=doc_ir)


def create_isolated_test_registry() -> ParserRegistry:
    registry = ParserRegistry()
    registry.register("pymupdf_native", FakeNativeParser)
    registry.register("paddleocr_vl", FakeFallbackParser)
    return registry


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

    registry = create_isolated_test_registry()
    router = ParserRouter(registry=registry)
    outcome = router.route_and_parse(source_doc, profile)

    assert outcome.routing_decision.requested_parser == "pymupdf_native"
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

    registry = create_isolated_test_registry()
    router = ParserRouter(registry=registry)
    outcome = router.route_and_parse(source_doc, profile, enable_fallback=True)

    assert outcome.routing_decision.attempt_number == 2
    assert outcome.routing_decision.fallback_trigger is not None
    assert outcome.fallback_result is not None
    assert outcome.selected_result.document_ir.full_text == "Fake Fallback Extracted Content"
