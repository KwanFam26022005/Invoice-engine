"""Optional real Docling semantic canary; never runs in the default suite."""

import os
from pathlib import Path

import fitz
import pytest

from document_engine.core.models import DocumentFamilyType, PDFProfileType
from document_engine.ir.models import (
    BlockIR,
    DocumentIR,
    DocumentProfile,
    PageIR,
    ParserProvenance,
    SourceDocument,
)
from document_engine.semantic import EvidenceGrounder, SemanticExtractionRequest
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
        pages=[
            PageIR(
                page_id="doc_semantic_canary_p0001",
                page_number=1,
                blocks=[
                    BlockIR(
                        block_id="b-number",
                        page_number=1,
                        text="Invoice No: INV-SYNTH-001",
                    ),
                    BlockIR(
                        block_id="b-total",
                        page_number=1,
                        text="Grand total: 1250000 VND",
                    ),
                ],
            )
        ],
    )
    request = SemanticExtractionRequest(
        document_id=source.document_id,
        family=DocumentFamilyType.SALES_INVOICE,
        target_schema_name="SalesInvoicePayload",
        document_ir=document_ir,
    )

    # CPU inference of a 2B VLM can take several minutes; keep this timeout
    # confined to the explicit opt-in canary rather than the production default.
    extractor = DoclingSemanticExtractor(timeout=900.0)
    health = extractor.healthcheck()
    assert health.success, health.error_type
    assert health.health_data is not None
    assert health.health_data.get("offline_runtime_ready") is True

    result = extractor.extract(request)
    assert result.success, result.error_code
    assert result.candidates

    grounding = EvidenceGrounder().ground_result(result, document_ir)
    assert grounding.grounded_count >= 1
