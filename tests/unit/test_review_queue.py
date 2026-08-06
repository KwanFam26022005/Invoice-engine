"""Unit tests for review queue and human corrections."""

from decimal import Decimal
from pathlib import Path
from document_engine.core.models import DocumentFamilyType
from document_engine.review.review_manager import ReviewManager
from document_engine.schemas.family_schemas import (
    BusinessDocumentEnvelope,
    CommonDocumentFields,
    SalesInvoicePayload,
)
from document_engine.storage.database import DuckDBStorage
from document_engine.validation.validator import BusinessValidator, ValidationIssue, ValidationSeverity


def test_review_queue_and_human_correction(tmp_path: Path):
    db_path = tmp_path / "review_test.duckdb"
    storage = DuckDBStorage(db_path)

    payload = SalesInvoicePayload(
        common=CommonDocumentFields(
            document_number="INV-ERR",
            grand_total=Decimal("100000.00"),
        )
    )
    envelope = BusinessDocumentEnvelope(
        document_id="doc_rev123",
        document_family=DocumentFamilyType.SALES_INVOICE,
        payload=payload,
    )

    validator = BusinessValidator()
    val_res = validator.validate(envelope)
    # Inject a review-required issue
    val_res.requires_review = True
    val_res.issues.append(
        ValidationIssue(
            code="MISSING_TAX_ID",
            severity=ValidationSeverity.WARNING,
            field_path="common.seller.tax_id",
            message="Seller Tax ID missing",
            review_required=True,
        )
    )

    storage.store_document(envelope, val_res)

    review_mgr = ReviewManager(storage)
    pending = review_mgr.list_pending_reviews()
    assert len(pending) == 1
    assert pending[0]["document_id"] == "doc_rev123"

    # Apply correction
    corr = review_mgr.apply_correction(
        document_id="doc_rev123",
        field_path="document_number",
        new_value="INV-CORRECTED",
        reviewer="auditor_01",
    )

    assert corr.new_value == "INV-CORRECTED"

    pending_after = review_mgr.list_pending_reviews()
    assert len(pending_after) == 0
