"""Unit tests for storage metadata correctness, NULL vs zero handling, parser attempts, and batch run lifecycle."""

from decimal import Decimal
from pathlib import Path

from document_engine.ir.models import SourceDocument
from document_engine.ir.models import DocumentParseResult
from document_engine.routing.parser_router import ParserRoutingOutcome, RoutingDecision
from document_engine.core.models import DocumentFamilyType, SourceFormatType
from document_engine.schemas.family_schemas import (
    BusinessDocumentEnvelope,
    CommonDocumentFields,
    SalesInvoicePayload,
)
from document_engine.storage.database import DuckDBStorage
from document_engine.validation.validator import ValidationResult


def create_sample_envelope(doc_id: str, grand_total: Decimal | None) -> BusinessDocumentEnvelope:
    payload = SalesInvoicePayload(
        common=CommonDocumentFields(
            document_number="INV-2026-001",
            issue_date="2026-08-07",
            currency="VND",
            grand_total=grand_total,
        ),
        line_items=[],
    )
    return BusinessDocumentEnvelope(
        document_id=doc_id,
        document_family=DocumentFamilyType.SALES_INVOICE,
        source_format=SourceFormatType.ELECTRONIC_DOCUMENT,
        payload=payload,
    )


def test_null_is_not_zero_in_database(tmp_path: Path):
    db_path = tmp_path / "test_null.duckdb"
    storage = DuckDBStorage(db_path)

    # Document 1: grand_total is None
    env_null = create_sample_envelope("doc_null", grand_total=None)
    storage.store_document(env_null, ValidationResult(is_valid=True, requires_review=False))

    # Document 2: grand_total is 0.0
    env_zero = create_sample_envelope("doc_zero", grand_total=Decimal("0.0"))
    storage.store_document(env_zero, ValidationResult(is_valid=True, requires_review=False))

    with storage.get_connection() as conn:
        row_null = conn.execute("SELECT grand_total FROM business_documents WHERE document_id='doc_null';").fetchone()
        row_zero = conn.execute("SELECT grand_total FROM business_documents WHERE document_id='doc_zero';").fetchone()

    assert row_null[0] is None
    assert row_zero[0] == 0.0


def test_real_source_document_metadata(tmp_path: Path):
    db_path = tmp_path / "test_meta.duckdb"
    storage = DuckDBStorage(db_path)

    env = create_sample_envelope("doc_real_meta", grand_total=Decimal("1500.0"))
    source_doc = SourceDocument(
        document_id="doc_real_meta",
        path="workspace/inbox/actual_invoice_2026.pdf",
        filename="actual_invoice_2026.pdf",
        sha256="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        page_count=3,
    )

    storage.store_document(env, ValidationResult(is_valid=True, requires_review=False), source_doc=source_doc)

    with storage.get_connection() as conn:
        row = conn.execute("SELECT filename, path, sha256, page_count FROM documents WHERE document_id='doc_real_meta';").fetchone()

    assert row[0] == "actual_invoice_2026.pdf"
    assert row[1] == "workspace/inbox/actual_invoice_2026.pdf"
    assert row[2] == "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    assert row[3] == 3


def test_processing_run_lifecycle(tmp_path: Path):
    db_path = tmp_path / "test_run.duckdb"
    storage = DuckDBStorage(db_path)

    run_id = "run_20260807_001"
    storage.start_processing_run(run_id, total_documents=10)

    with storage.get_connection() as conn:
        row_start = conn.execute("SELECT total_documents, status FROM processing_runs WHERE run_id=?;", [run_id]).fetchone()
    assert row_start[0] == 10
    assert row_start[1] == "running"

    storage.update_processing_run(run_id, processed_count=10, accepted_count=8, review_required_count=2, failed_count=0, status="completed")

    with storage.get_connection() as conn:
        row_end = conn.execute("SELECT processed_count, accepted_count, review_required_count, status, completed_at FROM processing_runs WHERE run_id=?;", [run_id]).fetchone()
    assert row_end[0] == 10
    assert row_end[1] == 8
    assert row_end[2] == 2
    assert row_end[3] == "completed"
    assert row_end[4] is not None


def test_running_processing_run_has_no_completed_timestamp(tmp_path: Path):
    storage = DuckDBStorage(tmp_path / "test_running.duckdb")
    storage.start_processing_run("run_still_running", total_documents=2)
    storage.update_processing_run(
        "run_still_running",
        processed_count=1,
        accepted_count=1,
        review_required_count=0,
        failed_count=0,
        status="running",
    )

    with storage.get_connection() as conn:
        completed_at, status = conn.execute(
            "SELECT completed_at, status FROM processing_runs WHERE run_id = ?;",
            ["run_still_running"],
        ).fetchone()
    assert status == "running"
    assert completed_at is None


def test_failed_parser_attempt_persistence(tmp_path: Path):
    """Requirement 5: Store parser attempts and document status 'failed' without requiring envelope."""
    db_path = tmp_path / "test_failed_parser.duckdb"
    storage = DuckDBStorage(db_path)

    source_doc = SourceDocument(
        document_id="doc_failed_001",
        path="workspace/inbox/corrupted.pdf",
        filename="corrupted.pdf",
        sha256="abc123sha256",
        page_count=1,
    )

    primary = DocumentParseResult(success=False, error_message="primary unavailable")
    fallback = DocumentParseResult(success=False, error_message="fallback unavailable")
    decision = RoutingDecision(
        requested_parser="primary_parser",
        actual_parser="primary_parser",
        selection_reason="both failed",
        fallback_trigger="Primary parser unavailable; fallback attempted.",
        fallback_requested_parser="fallback_parser",
        fallback_actual_parser="fallback_parser",
    )
    outcome = ParserRoutingOutcome(
        primary_result=primary,
        fallback_result=fallback,
        selected_result=fallback,
        selection_reason="both failed",
        routing_decision=decision,
    )
    storage.store_failed_document(
        source_doc=source_doc,
        routing_outcome=outcome,
        run_id="run_fail_001",
    )

    with storage.get_connection() as conn:
        row_doc = conn.execute("SELECT status, filename FROM documents WHERE document_id='doc_failed_001';").fetchone()
        attempts = conn.execute(
            """
            SELECT requested_parser, actual_parser, attempt_number, fallback_type,
                   success, execution_time_seconds, selected
            FROM parser_attempts WHERE document_id = ? ORDER BY attempt_number;
            """,
            ["doc_failed_001"],
        ).fetchall()

    assert row_doc[0] == "failed"
    assert row_doc[1] == "corrupted.pdf"
    assert attempts == [
        ("primary_parser", "primary_parser", 1, None, False, None, False),
        ("fallback_parser", "fallback_parser", 2, "primary_unavailable", False, None, True),
    ]
