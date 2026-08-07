"""Unit tests for versioned review workflow, correction history, and relational reprojection."""

from decimal import Decimal
from pathlib import Path

from document_engine.core.models import DocumentFamilyType, SourceFormatType
from document_engine.review.review_manager import ReviewManager
from document_engine.schemas.family_schemas import (
    BusinessDocumentEnvelope,
    CommonDocumentFields,
    Party,
    SalesInvoicePayload,
)
from document_engine.storage.database import DuckDBStorage
from document_engine.validation.validator import ValidationResult


def test_versioned_human_correction_and_reprojection(tmp_path: Path):
    db_path = tmp_path / "test_review.duckdb"
    storage = DuckDBStorage(db_path)
    review_mgr = ReviewManager(storage)

    doc_id = "doc_test_corr_001"
    payload = SalesInvoicePayload(
        common=CommonDocumentFields(
            document_number="INV-100",
            issue_date="2026-08-07",
            currency="VND",
            grand_total=Decimal("100.0"),
            seller=Party(tax_id="0101112222", name="Old Seller"),
        ),
        line_items=[],
    )
    envelope = BusinessDocumentEnvelope(
        document_id=doc_id,
        document_family=DocumentFamilyType.SALES_INVOICE,
        source_format=SourceFormatType.ELECTRONIC_DOCUMENT,
        payload=payload,
    )

    # 1. Store initial machine envelope
    storage.store_document(envelope, ValidationResult(is_valid=True, requires_review=True))

    # Verify initial v1 canonical version
    v1 = review_mgr.get_latest_canonical_version(doc_id)
    assert v1 is not None
    assert v1["version_number"] == 1
    assert v1["source"] == "machine_extracted"

    # 2. Apply human correction to common.grand_total from 100 to 120
    corr = review_mgr.apply_correction(
        document_id=doc_id,
        field_path="common.grand_total",
        new_value=Decimal("120.0"),
        reviewer="auditor_jane",
        reason="corrected_invoice_total",
    )

    assert corr.old_value == "100.0"
    assert corr.new_value == "120.0"
    assert corr.reviewer == "auditor_jane"

    # Verify new v2 canonical version created
    v2 = review_mgr.get_latest_canonical_version(doc_id)
    assert v2 is not None
    assert v2["version_number"] == 2
    assert v2["source"] == "human_corrected"

    # Verify relational database table business_documents.grand_total updated to 120.0
    with storage.get_connection() as conn:
        row_doc = conn.execute("SELECT grand_total FROM business_documents WHERE document_id = ?;", [doc_id]).fetchone()
        row_corr = conn.execute("SELECT old_value, new_value, reviewer FROM review_corrections WHERE document_id = ?;", [doc_id]).fetchone()

    assert row_doc[0] == 120.0
    assert row_corr[0] == "100.0"
    assert row_corr[1] == "120.0"
    assert row_corr[2] == "auditor_jane"
