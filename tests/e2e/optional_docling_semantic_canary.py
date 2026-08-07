"""Optional real Docling semantic canary; never runs in the default suite."""

import os
from pathlib import Path

import fitz
import pytest

from document_engine.core.models import DocumentFamilyType, PDFProfileType
from document_engine.ir.models import DocumentIR, DocumentProfile, PageIR, ParserProvenance, SourceDocument
from document_engine.semantic import SemanticExtractionRequest
from document_engine.semantic.extractors import DoclingSemanticExtractor


pytestmark = pytest.mark.optional_engine


def test_docling_semantic_real_synthetic_canary(tmp_path: Path):
    if os.getenv("RUN_OPTIONAL_ENGINE_TESTS") != "1":
        pytest.skip("RUN_OPTIONAL_ENGINE_TESTS is not enabled")
    if not os.getenv("DOCLING_SEMANTIC_ARTIFACTS_PATH"):
        pytest.skip("DOCLING_SEMANTIC_ARTIFACTS_PATH is not configured")

    pdf_path = tmp_path / "synthetic_invoice.pdf"
    pdf = fitz.open()
    page = pdf.new_page()
    page.insert_text((72, 72), "Invoice No: INV-SYNTH-001")
    page.insert_text((72, 100), "Grand total: 1250000 VND")
    pdf.save(pdf_path)
    pdf.close()

    source = SourceDocument(
        document_id="doc_semantic_canary",
        filename=pdf_path.name,
        path=str(pdf_path),
        sha256="synthetic-canary",
        page_count=1,
    )
    document_ir = DocumentIR(
        document_id=source.document_id,
        source_document=source,
        profile=DocumentProfile(
            pdf_profile=PDFProfileType.NATIVE_PDF,
            has_text_layer=True,
        ),
        provenance=ParserProvenance(parser_id="synthetic", parser_version="1"),
        pages=[PageIR(page_id="doc_semantic_canary_p0001", page_number=1)],
    )
    request = SemanticExtractionRequest(
        document_id=source.document_id,
        family=DocumentFamilyType.SALES_INVOICE,
        target_schema_name="SalesInvoicePayload",
        document_ir=document_ir,
    )

    extractor = DoclingSemanticExtractor(timeout=300.0)
    health = extractor.healthcheck()
    assert health.success, health.error_type
    result = extractor.extract(request)
    assert result.success, result.error_code
    assert isinstance(result.candidates, list)
