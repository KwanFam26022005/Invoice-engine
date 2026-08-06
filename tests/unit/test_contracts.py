"""Unit tests for core data contracts and enums."""


from document_benchmark.core.contracts import (
    BenchmarkRunSpec,
    DocumentInput,
    EngineSpec,
    RawExtractionResult,
)
from document_benchmark.core.statuses import (
    ExecutionMode,
    OutputKind,
)


def test_engine_spec_defaults():
    spec = EngineSpec(
        engine_id="mock",
        config_id="mock_test",
    )
    assert spec.engine_id == "mock"
    assert spec.config_id == "mock_test"
    assert spec.enabled is True
    assert spec.supports_pdf_text is True
    assert spec.output_kind == OutputKind.DOCUMENT_IR


def test_document_input_creation():
    doc = DocumentInput(
        document_id="doc_123",
        path="datasets/documents/sample_invoice.pdf",
        filename="sample_invoice.pdf",
        sha256="abc123hash",
        page_count=2,
    )
    assert doc.document_id == "doc_123"
    assert doc.mime_type == "application/pdf"
    assert doc.page_count == 2


def test_raw_extraction_result_serialization():
    res = RawExtractionResult(
        run_id="run_1",
        document_id="doc_1",
        engine_id="mock",
        config_id="mock_default",
        success=True,
        full_text="Sample text",
        pages=[{"page_number": 1, "text": "Sample text"}],
    )
    data = res.model_dump()
    assert data["success"] is True
    assert data["engine_id"] == "mock"
    assert len(data["pages"]) == 1


def test_benchmark_run_spec():
    spec = BenchmarkRunSpec(
        run_id="run_test",
        document_ids=["doc_1", "doc_2"],
        engine_config_ids=["mock_default"],
        execution_mode=ExecutionMode.BOTH,
    )
    assert spec.run_id == "run_test"
    assert len(spec.document_ids) == 2
    assert spec.warmup_runs == 1
    assert spec.measured_runs == 3
