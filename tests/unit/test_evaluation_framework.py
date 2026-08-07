"""Unit tests for evaluation framework, audit comparator, metrics, and failure taxonomy."""

from decimal import Decimal

from document_engine.core.models import DocumentFamilyType, SourceFormatType
from document_engine.evaluation.audit_models import DocumentAuditSpec, FieldAuditEntry, FieldAuditStatus
from document_engine.evaluation.comparator import compare_values
from document_engine.evaluation.metrics import Evaluator
from document_engine.orchestration.pipeline import PipelineResult
from document_engine.schemas.family_schemas import (
    BusinessDocumentEnvelope,
    CommonDocumentFields,
    FieldCandidate,
    Party,
    SalesInvoicePayload,
)


def test_compare_values_domain_normalizations():
    # Tax ID comparison
    exact, norm = compare_values("010 999 8888", "0109998888", "common.seller.tax_id")
    assert exact is False
    assert norm is True

    # Decimal comparison within tolerance
    _exact_d, norm_d = compare_values(Decimal("100.00"), Decimal("100.005"), "common.grand_total", tolerance=0.01)
    assert norm_d is True

    # String Unicode NFC trimming
    _exact_s, norm_s = compare_values("Công ty ABC  ", "công ty abc", "common.seller.name")
    assert norm_s is True


def test_evaluator_confirmed_denominator_rule():
    evaluator = Evaluator()

    # Create synthetic pipeline result
    payload = SalesInvoicePayload(
        common=CommonDocumentFields(
            document_number="INV-001",
            issue_date="2026-08-07",
            grand_total=Decimal("500.0"),
            seller=Party(tax_id="0109998888"),
        )
    )
    envelope = BusinessDocumentEnvelope(
        document_id="doc_eval_01",
        document_family=DocumentFamilyType.SALES_INVOICE,
        source_format=SourceFormatType.ELECTRONIC_DOCUMENT,
        payload=payload,
        field_candidates={
            "common.document_number": FieldCandidate(value="INV-001"),
            "common.grand_total": FieldCandidate(value=Decimal("500.0")),
        },
    )

    pipeline_res = PipelineResult(
        document_id="doc_eval_01",
        pdf_profile="native_pdf",
        selected_parser="pymupdf_native",
        document_family="sales_invoice",
        validation_status="accepted",
        requires_review=False,
        database_path="memory",
        envelope=envelope,
    )

    # Audit Spec with 2 CONFIRMED fields and 1 NOT_AUDITED field
    audit_spec = DocumentAuditSpec(
        document_id="doc_eval_01",
        family="sales_invoice",
        fields={
            "common.document_number": FieldAuditEntry(expected="INV-001", status=FieldAuditStatus.CONFIRMED),
            "common.grand_total": FieldAuditEntry(expected=Decimal("500.0"), status=FieldAuditStatus.CONFIRMED),
            "common.seller.tax_id": FieldAuditEntry(expected="0109998888", status=FieldAuditStatus.NOT_AUDITED),
        },
    )

    summary = evaluator.evaluate_document(pipeline_res, audit_spec)

    # Denominator MUST only count the 2 CONFIRMED fields (NOT_AUDITED excluded)
    assert summary.audited_field_count == 2
    assert summary.exact_match_count == 2
    assert summary.normalized_match_count == 2
    assert summary.wrong_value_count == 0

    agg = evaluator.aggregate_summaries([summary])
    assert agg.total_audited_fields == 2
    assert agg.exact_match_rate == 1.0
    assert agg.normalized_match_rate == 1.0
