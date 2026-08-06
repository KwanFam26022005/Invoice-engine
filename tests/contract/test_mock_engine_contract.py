"""Contract test for MockEngine validating DocumentEngine interface contract."""

from document_benchmark.core.contracts import DocumentInput, EngineSpec
from document_benchmark.core.statuses import EngineStatus
from document_benchmark.engines.mock_engine import MockEngine


def test_mock_engine_lifecycle():
    spec = EngineSpec(
        engine_id="mock",
        config_id="mock_contract",
        options={"prepare_delay_ms": 5, "extract_delay_ms": 10, "mock_family": "invoice"},
    )
    engine = MockEngine(spec)

    # 1. Healthcheck
    health = engine.healthcheck()
    assert health.available is True
    assert health.status == EngineStatus.SUCCESS

    # 2. Prepare
    engine.prepare()
    assert engine._is_prepared is True

    # 3. Extract
    doc = DocumentInput(
        document_id="test_doc",
        path="datasets/documents/sample_invoice.pdf",
        filename="sample_invoice.pdf",
        sha256="dummyhash",
        page_count=2,
    )
    res = engine.extract(doc)
    assert res.success is True
    assert res.document_id == "test_doc"
    assert len(res.pages) == 2
    assert "invoice_number" in res.field_candidates
    assert res.execution_time_ms > 0

    # 4. Close
    engine.close()
    assert engine._is_prepared is False


def test_mock_engine_failure_injection():
    spec = EngineSpec(
        engine_id="mock",
        config_id="mock_fail",
        options={"should_fail": True, "failure_reason": "Injected test failure"},
    )
    engine = MockEngine(spec)
    engine.prepare()

    doc = DocumentInput(
        document_id="test_doc_fail",
        path="datasets/documents/sample_invoice.pdf",
        filename="sample_invoice.pdf",
        sha256="dummyhash",
        page_count=1,
    )
    res = engine.extract(doc)

    assert res.success is False
    assert res.error_type == "MockExtractionFailure"
    assert "Injected test failure" in res.error_message
    engine.close()
