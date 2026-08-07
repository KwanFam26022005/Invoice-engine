"""Unit tests for evaluation framework, audit comparator, metrics, and failure taxonomy."""

from decimal import Decimal
from document_engine.core.models import DocumentFamilyType, SourceFormatType
from document_engine.evaluation.audit_models import DocumentAuditSpec, FieldAuditEntry, FieldAuditStatus
from document_engine.evaluation.comparator import compare_values
from document_engine.evaluation.metrics import DocumentEvaluationSummary, Evaluator
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


def test_metric_denominator_confirmed_only():
    """Requirement 1: Only CONFIRMED audit status is included in audited denominator."""
    evaluator = Evaluator()

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

    # Audit Spec with 2 CONFIRMED fields, 1 NOT_PRESENT_IN_SOURCE, 1 AMBIGUOUS_SOURCE, 1 NOT_AUDITED
    audit_spec = DocumentAuditSpec(
        document_id="doc_eval_01",
        family="sales_invoice",
        fields={
            "common.document_number": FieldAuditEntry(expected="INV-001", status=FieldAuditStatus.CONFIRMED),
            "common.grand_total": FieldAuditEntry(expected=Decimal("500.0"), status=FieldAuditStatus.CONFIRMED),
            "common.seller.name": FieldAuditEntry(expected=None, status=FieldAuditStatus.NOT_PRESENT_IN_SOURCE),
            "common.issue_date": FieldAuditEntry(expected="2026-08-07", status=FieldAuditStatus.AMBIGUOUS_SOURCE),
            "common.seller.tax_id": FieldAuditEntry(expected="0109998888", status=FieldAuditStatus.NOT_AUDITED),
        },
    )

    summary = evaluator.evaluate_document(pipeline_res, audit_spec)

    # Denominator MUST only count the 2 CONFIRMED fields
    assert summary.audited_field_count == 2
    assert summary.exact_match_count == 2
    assert summary.normalized_match_count == 2
    assert summary.wrong_value_count == 0


def test_exact_vs_normalized_match_independent():
    """Requirement 2: exact=False, normalized=True increments norm_cnt by 1 and exact_cnt by 0."""
    evaluator = Evaluator()

    payload = SalesInvoicePayload(
        common=CommonDocumentFields(
            document_number="INV-001",
            seller=Party(tax_id="010 999 8888"),
        )
    )
    envelope = BusinessDocumentEnvelope(
        document_id="doc_eval_02",
        document_family=DocumentFamilyType.SALES_INVOICE,
        source_format=SourceFormatType.ELECTRONIC_DOCUMENT,
        payload=payload,
        field_candidates={
            "common.seller.tax_id": FieldCandidate(value="010 999 8888"),
        },
    )

    pipeline_res = PipelineResult(
        document_id="doc_eval_02",
        pdf_profile="native_pdf",
        selected_parser="pymupdf_native",
        document_family="sales_invoice",
        validation_status="accepted",
        requires_review=False,
        database_path="memory",
        envelope=envelope,
    )

    audit_spec = DocumentAuditSpec(
        document_id="doc_eval_02",
        family="sales_invoice",
        fields={
            "common.seller.tax_id": FieldAuditEntry(expected="0109998888", status=FieldAuditStatus.CONFIRMED),
        },
    )

    summary = evaluator.evaluate_document(pipeline_res, audit_spec)

    assert summary.audited_field_count == 1
    assert summary.exact_match_count == 0
    assert summary.normalized_match_count == 1


def test_aggregate_evidence_coverage_total_fields():
    """Requirement 3: Aggregate evidence coverage uses total evidence supported over total confirmed fields."""
    from document_engine.schemas.family_schemas import EvidenceReference
    evaluator = Evaluator()

    payload = SalesInvoicePayload(common=CommonDocumentFields(document_number="INV-1"))
    env1 = BusinessDocumentEnvelope(
        document_id="doc1",
        document_family=DocumentFamilyType.SALES_INVOICE,
        source_format=SourceFormatType.ELECTRONIC_DOCUMENT,
        payload=payload,
        field_candidates={
            "common.document_number": FieldCandidate(value="INV-1", evidence_references=[EvidenceReference(document_id="doc1", page_number=1)]),
        },
    )
    p1 = PipelineResult(
        document_id="doc1",
        pdf_profile="native_pdf",
        selected_parser="pymupdf",
        document_family="sales_invoice",
        validation_status="accepted",
        requires_review=False,
        database_path="m",
        envelope=env1,
    )
    spec1 = DocumentAuditSpec(
        document_id="doc1",
        family="sales_invoice",
        fields={"common.document_number": FieldAuditEntry(expected="INV-1", status=FieldAuditStatus.CONFIRMED)},
    )
    s1 = evaluator.evaluate_document(p1, spec1)

    env2 = BusinessDocumentEnvelope(
        document_id="doc2",
        document_family=DocumentFamilyType.SALES_INVOICE,
        source_format=SourceFormatType.ELECTRONIC_DOCUMENT,
        payload=payload,
        field_candidates={
            "common.document_number": FieldCandidate(value="INV-1", evidence_references=[]),
            "common.issue_date": FieldCandidate(value="2026-08-07", evidence_references=[]),
            "common.currency": FieldCandidate(value="VND", evidence_references=[]),
        },
    )
    p2 = PipelineResult(
        document_id="doc2",
        pdf_profile="native_pdf",
        selected_parser="pymupdf",
        document_family="sales_invoice",
        validation_status="accepted",
        requires_review=False,
        database_path="m",
        envelope=env2,
    )
    spec2 = DocumentAuditSpec(
        document_id="doc2",
        family="sales_invoice",
        fields={
            "common.document_number": FieldAuditEntry(expected="INV-1", status=FieldAuditStatus.CONFIRMED),
            "common.issue_date": FieldAuditEntry(expected="2026-08-07", status=FieldAuditStatus.CONFIRMED),
            "common.currency": FieldAuditEntry(expected="VND", status=FieldAuditStatus.CONFIRMED),
        },
    )
    s2 = evaluator.evaluate_document(p2, spec2)

    agg = evaluator.aggregate_summaries([s1, s2])
    # Doc 1: 1/1 evidence (1.0). Doc 2: 0/3 evidence (0.0).
    # Total evidence supported = 1, Total confirmed fields = 4.
    # Overall coverage MUST be 1 / 4 = 0.25 (NOT (1.0 + 0.0)/2 = 0.50).
    assert agg.total_audited_fields == 4
    assert agg.total_evidence_supported_fields == 1
    assert agg.overall_evidence_coverage == 0.25


def test_aggregate_audited_documents_requires_confirmed_fields():
    evaluator = Evaluator()
    summaries = [
        DocumentEvaluationSummary(
            document_id="doc-a",
            family="sales_invoice",
            pdf_profile="native_pdf",
            selected_parser="synthetic",
            validation_status="accepted",
            audited_field_count=2,
        ),
        DocumentEvaluationSummary(
            document_id="doc-b",
            family="sales_invoice",
            pdf_profile="native_pdf",
            selected_parser="synthetic",
            validation_status="accepted",
            audited_field_count=0,
        ),
        DocumentEvaluationSummary(
            document_id="doc-c",
            family="unknown",
            pdf_profile="native_pdf",
            selected_parser="synthetic",
            validation_status="failed",
            audited_field_count=0,
        ),
    ]

    report = evaluator.aggregate_summaries(summaries)

    assert report.audited_documents == 1
