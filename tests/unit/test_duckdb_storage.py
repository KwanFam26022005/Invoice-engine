"""Unit tests for DuckDB storage engine."""

from decimal import Decimal
from pathlib import Path
from document_engine.core.models import DocumentFamilyType
from document_engine.schemas.family_schemas import (
    BusinessDocumentEnvelope,
    CommonDocumentFields,
    SalesInvoicePayload,
)
from document_engine.storage.database import DuckDBStorage
from document_engine.validation.validator import BusinessValidator


def test_duckdb_schema_initialization_and_store(tmp_path: Path):
    db_path = tmp_path / "test_engine.duckdb"
    storage = DuckDBStorage(db_path)

    payload = SalesInvoicePayload(
        common=CommonDocumentFields(
            document_number="INV-999",
            grand_total=Decimal("12500000.00"),
        )
    )
    envelope = BusinessDocumentEnvelope(
        document_id="doc_duck123",
        document_family=DocumentFamilyType.SALES_INVOICE,
        payload=payload,
    )

    validator = BusinessValidator()
    val_res = validator.validate(envelope)

    storage.store_document(envelope, val_res, run_id="run_test")

    with storage.get_connection() as conn:
        doc_count = conn.execute("SELECT COUNT(*) FROM business_documents;").fetchone()[0]
        assert doc_count == 1

        row = conn.execute(
            "SELECT document_number, grand_total FROM business_documents WHERE document_id='doc_duck123';"
        ).fetchone()
        assert row[0] == "INV-999"
        assert row[1] == 12500000.0
