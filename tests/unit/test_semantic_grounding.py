"""Synthetic regression tests for deterministic semantic evidence grounding."""

from decimal import Decimal

import pytest

from document_engine.core.models import DocumentFamilyType, PDFProfileType
from document_engine.ir.models import (
    BlockIR,
    DocumentIR,
    DocumentProfile,
    Geometry,
    PageIR,
    ParserProvenance,
    SourceDocument,
    TableCellIR,
    TableIR,
)
from document_engine.semantic import (
    EvidenceGrounder,
    GroundingMethod,
    GroundingStatus,
    SemanticCandidate,
    SemanticCandidateStatus,
    SemanticEvidenceHint,
    SemanticExtractionResult,
)


def _document() -> DocumentIR:
    source = SourceDocument(
        document_id="doc_grounding",
        filename="synthetic.pdf",
        path="synthetic.pdf",
        sha256="synthetic-hash",
        page_count=1,
    )
    profile = DocumentProfile(
        pdf_profile=PDFProfileType.NATIVE_PDF,
        has_text_layer=True,
        text_character_count=200,
    )
    blocks = [
        BlockIR(
            block_id="b-number",
            page_number=1,
            text="Số hóa đơn: INV-001",
            geometry=Geometry(bbox=[10, 10, 200, 30]),
        ),
        BlockIR(
            block_id="b-total",
            page_number=1,
            text="Tổng thanh toán: 1.250.000 VND",
            geometry=Geometry(bbox=[10, 40, 250, 60]),
        ),
        BlockIR(
            block_id="b-date",
            page_number=1,
            text="Ngày lập: 07/08/2026",
        ),
        BlockIR(
            block_id="b-tax",
            page_number=1,
            text="Mã số thuế: 0 1 0 1 2 3 4 5 6 7",
        ),
        BlockIR(
            block_id="b-party",
            page_number=1,
            text="Công ty Cổ phần Ví dụ",
        ),
    ]
    table = TableIR(
        table_id="t1",
        page_number=1,
        row_count=2,
        col_count=1,
        cells=[
            TableCellIR(cell_id="c-header", row_index=0, col_index=0, text="Mô tả"),
            TableCellIR(
                cell_id="c-value",
                row_index=1,
                col_index=0,
                text="Dịch vụ vận chuyển",
                geometry=Geometry(bbox=[20, 100, 180, 120]),
            ),
        ],
    )
    page = PageIR(
        page_id="p1",
        page_number=1,
        blocks=blocks,
        tables=[table],
        text_content="\n".join(block.text for block in blocks),
    )
    return DocumentIR(
        document_id="doc_grounding",
        source_document=source,
        profile=profile,
        provenance=ParserProvenance(parser_id="synthetic", parser_version="1.0"),
        pages=[page],
        full_text=page.text_content,
    )


def _candidate(field_path: str, value, raw_value=None, **kwargs) -> SemanticCandidate:
    return SemanticCandidate(
        field_path=field_path,
        value=value,
        raw_value=raw_value,
        source_method="synthetic_semantic",
        **kwargs,
    )


def test_ground_exact_block_value_and_preserve_provenance():
    grounded = EvidenceGrounder().ground(
        _candidate("common.document_number", "INV-001"),
        _document(),
    )

    assert grounded.grounding_status == GroundingStatus.GROUNDED
    assert grounded.match_method == GroundingMethod.EXACT_SOURCE
    assert grounded.evidence_references[0].block_id == "b-number"
    assert grounded.evidence_references[0].bbox == [10, 10, 200, 30]
    assert grounded.evidence_references[0].parser_id == "synthetic"


def test_ground_table_cell_value_with_cell_reference():
    grounded = EvidenceGrounder().ground(
        _candidate("line_items[0].description", "Dịch vụ vận chuyển"),
        _document(),
    )

    assert grounded.grounding_status == GroundingStatus.GROUNDED
    evidence = grounded.evidence_references[0]
    assert evidence.table_id == "t1"
    assert evidence.cell_id == "c-value"
    assert evidence.bbox == [20, 100, 180, 120]


def test_ground_normalized_unicode_case_and_whitespace():
    grounded = EvidenceGrounder().ground(
        _candidate("common.seller.name", "công ty   cổ phần ví dụ"),
        _document(),
    )

    assert grounded.grounding_status == GroundingStatus.GROUNDED
    assert grounded.match_method == GroundingMethod.NORMALIZED_TEXT


def test_ground_decimal_by_canonical_value_without_numeric_substring_false_positive():
    grounded = EvidenceGrounder().ground(
        _candidate("common.grand_total", Decimal("1250000")),
        _document(),
    )
    wrong_quantity = EvidenceGrounder().ground(
        _candidate("line_items[0].quantity", Decimal("1")),
        _document(),
    )

    assert grounded.grounding_status == GroundingStatus.GROUNDED
    assert grounded.match_method == GroundingMethod.DECIMAL_CANONICAL
    assert grounded.evidence_references[0].block_id == "b-total"
    assert wrong_quantity.grounding_status == GroundingStatus.UNSUPPORTED


def test_raw_value_cannot_ground_a_different_canonical_value():
    grounded = EvidenceGrounder().ground(
        _candidate(
            "common.grand_total",
            Decimal("999"),
            raw_value="Tổng thanh toán: 1.250.000 VND",
        ),
        _document(),
    )

    assert grounded.grounding_status == GroundingStatus.UNSUPPORTED
    assert grounded.evidence_references == []


def test_ground_date_by_canonical_value():
    grounded = EvidenceGrounder().ground(
        _candidate("common.issue_date", "2026-08-07"),
        _document(),
    )

    assert grounded.grounding_status == GroundingStatus.GROUNDED
    assert grounded.match_method == GroundingMethod.DATE_CANONICAL
    assert grounded.evidence_references[0].block_id == "b-date"


def test_ground_spaced_tax_id_by_canonical_value():
    grounded = EvidenceGrounder().ground(
        _candidate("common.seller.tax_id", "0101234567"),
        _document(),
    )

    assert grounded.grounding_status == GroundingStatus.GROUNDED
    assert grounded.match_method == GroundingMethod.TAX_ID_CANONICAL
    assert grounded.evidence_references[0].block_id == "b-tax"


def test_fuzzy_text_is_allowed_only_for_noncritical_text_fields():
    grounded = EvidenceGrounder(fuzzy_threshold=0.9).ground(
        _candidate("common.seller.name", "Công ty Cổ phần Vi dụ"),
        _document(),
    )
    critical = EvidenceGrounder(fuzzy_threshold=0.5).ground(
        _candidate("common.document_number", "INV-OO1"),
        _document(),
    )

    assert grounded.grounding_status == GroundingStatus.GROUNDED
    assert grounded.match_method == GroundingMethod.FUZZY_TEXT
    assert critical.grounding_status == GroundingStatus.UNSUPPORTED
    assert critical.match_method == GroundingMethod.NONE


def test_hints_are_prioritized_but_do_not_create_false_evidence():
    candidate = _candidate(
        "common.document_number",
        "INV-001",
        evidence_hints=[SemanticEvidenceHint(page_number=1, block_id="b-party")],
    )
    grounded = EvidenceGrounder().ground(candidate, _document())

    assert grounded.grounding_status == GroundingStatus.GROUNDED
    assert grounded.evidence_references[0].block_id == "b-number"


def test_bbox_hint_can_prioritize_the_actual_source_region():
    candidate = _candidate(
        "common.document_number",
        "INV-001",
        evidence_hints=[SemanticEvidenceHint(page_number=1, bbox=[10, 10, 200, 30])],
    )
    grounded = EvidenceGrounder().ground(candidate, _document())

    assert grounded.grounding_status == GroundingStatus.GROUNDED
    assert grounded.evidence_references[0].block_id == "b-number"


def test_compound_candidates_require_atomic_decomposition():
    grounded = EvidenceGrounder().ground(
        _candidate("line_items", [{"description": "Dịch vụ vận chuyển"}]),
        _document(),
    )

    assert grounded.grounding_status == GroundingStatus.UNSUPPORTED
    assert "decomposed" in grounded.warnings[0]


def test_abstained_and_unsupported_candidates_remain_non_grounded():
    abstained = SemanticCandidate(
        field_path="common.grand_total",
        value=None,
        source_method="synthetic_semantic",
        status=SemanticCandidateStatus.ABSTAINED,
    )
    unsupported = SemanticCandidate(
        field_path="common.document_number",
        value=None,
        source_method="synthetic_semantic",
        status=SemanticCandidateStatus.UNSUPPORTED,
    )

    abstained_result = EvidenceGrounder().ground(abstained, _document())
    unsupported_result = EvidenceGrounder().ground(unsupported, _document())

    assert abstained_result.grounding_status == GroundingStatus.ABSTAINED
    assert abstained_result.evidence_references == []
    assert unsupported_result.grounding_status == GroundingStatus.UNSUPPORTED
    assert unsupported_result.evidence_references == []


def test_ground_result_enforces_document_identity_and_reports_counts():
    result = SemanticExtractionResult(
        extractor_id="synthetic",
        extractor_version="1",
        document_id="doc_grounding",
        family=DocumentFamilyType.SALES_INVOICE,
        candidates=[
            _candidate("common.document_number", "INV-001"),
            _candidate("common.document_number", "NOT-IN-SOURCE"),
            SemanticCandidate(
                field_path="common.grand_total",
                value=None,
                source_method="synthetic_semantic",
                status=SemanticCandidateStatus.ABSTAINED,
            ),
        ],
    )

    report = EvidenceGrounder().ground_result(result, _document())

    assert report.grounded_count == 1
    assert report.unsupported_count == 1
    assert report.abstained_count == 1

    wrong = result.model_copy(update={"document_id": "doc_other"})
    with pytest.raises(ValueError, match="one document"):
        EvidenceGrounder().ground_result(wrong, _document())
