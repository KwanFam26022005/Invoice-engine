"""Tests for engine-agnostic semantic extraction contracts."""

import pytest
from pydantic import ValidationError

from document_engine.core.models import DocumentFamilyType, PDFProfileType
from document_engine.ir.models import (
    DocumentIR,
    DocumentProfile,
    PageIR,
    ParserProvenance,
    SourceDocument,
)
from document_engine.semantic import (
    SemanticCandidate,
    SemanticCandidateStatus,
    SemanticExtractionPolicy,
    SemanticExtractionRequest,
    SemanticExtractionResult,
    SemanticExtractor,
)


def _document(document_id: str = "doc-semantic") -> DocumentIR:
    return DocumentIR(
        document_id=document_id,
        source_document=SourceDocument(
            document_id=document_id,
            filename="synthetic.pdf",
            path="synthetic.pdf",
            sha256="synthetic-hash",
            page_count=1,
        ),
        profile=DocumentProfile(
            pdf_profile=PDFProfileType.NATIVE_PDF,
            has_text_layer=True,
        ),
        provenance=ParserProvenance(
            parser_id="synthetic",
            parser_version="1",
        ),
        pages=[PageIR(page_id="p1", page_number=1, text_content="synthetic")],
        full_text="synthetic",
    )


def test_semantic_request_is_local_first_by_default():
    request = SemanticExtractionRequest(
        document_id="doc-semantic",
        family=DocumentFamilyType.SALES_INVOICE,
        target_schema_name="SalesInvoicePayload",
        document_ir=_document(),
    )

    assert request.policy.local_runtime_only is True
    assert request.policy.allow_network is False
    assert request.policy.abstain_on_uncertain is True


def test_semantic_request_rejects_document_id_mismatch():
    with pytest.raises(ValidationError):
        SemanticExtractionRequest(
            document_id="different",
            family=DocumentFamilyType.SALES_INVOICE,
            target_schema_name="SalesInvoicePayload",
            document_ir=_document(),
        )


def test_semantic_candidate_confidence_is_bounded_and_abstention_is_null():
    with pytest.raises(ValidationError):
        SemanticCandidate(
            field_path="common.grand_total",
            value="100",
            confidence=1.5,
            source_method="synthetic",
        )

    with pytest.raises(ValidationError):
        SemanticCandidate(
            field_path="common.grand_total",
            value="100",
            source_method="synthetic",
            status=SemanticCandidateStatus.ABSTAINED,
        )


def test_semantic_policy_rejects_network_for_local_runtime():
    with pytest.raises(ValidationError):
        SemanticExtractionPolicy(local_runtime_only=True, allow_network=True)


def test_semantic_result_groups_candidates_without_promoting_to_truth():
    result = SemanticExtractionResult(
        extractor_id="synthetic",
        extractor_version="1",
        document_id="doc-semantic",
        family=DocumentFamilyType.SALES_INVOICE,
        candidates=[
            SemanticCandidate(
                field_path="common.grand_total",
                value="100",
                confidence=0.9,
                source_method="synthetic",
            ),
            SemanticCandidate(
                field_path="common.grand_total",
                value="101",
                confidence=0.8,
                source_method="synthetic",
            ),
        ],
    )

    assert len(result.candidates_by_field()["common.grand_total"]) == 2


def test_semantic_extractor_protocol_accepts_structural_implementation():
    class FakeExtractor:
        extractor_id = "fake"

        def supports(self, family, target_schema_name, document_ir):
            return True

        def extract(self, request):
            return SemanticExtractionResult(
                extractor_id=self.extractor_id,
                document_id=request.document_id,
                family=request.family,
            )

    extractor = FakeExtractor()

    assert isinstance(extractor, SemanticExtractor)
    assert extractor.extract(
        SemanticExtractionRequest(
            document_id="doc-semantic",
            family=DocumentFamilyType.SALES_INVOICE,
            target_schema_name="SalesInvoicePayload",
            document_ir=_document(),
        )
    ).success
