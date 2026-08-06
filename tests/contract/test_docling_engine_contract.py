"""Contract test for DoclingEngine adapter."""

from document_benchmark.core.contracts import DocumentInput, EngineSpec
from document_benchmark.core.statuses import EngineStatus
from document_benchmark.engines.docling_engine import DoclingEngine, _check_docling_import


def test_docling_engine_healthcheck():
    spec = EngineSpec(
        engine_id="docling",
        config_id="docling_text_only_cpu",
        options={"do_ocr": False, "do_table_structure": False},
    )
    engine = DoclingEngine(spec)
    health = engine.healthcheck()

    is_installed, _, _ = _check_docling_import()
    if is_installed:
        assert health.available is True
        assert health.status == EngineStatus.SUCCESS
    else:
        assert health.available is False
        assert health.status == EngineStatus.UNAVAILABLE
        assert "docling" in health.missing_dependencies


def test_docling_engine_extraction():
    is_installed, _, _ = _check_docling_import()
    if not is_installed:
        return

    spec = EngineSpec(
        engine_id="docling",
        config_id="docling_text_only_cpu",
        options={"do_ocr": False, "do_table_structure": False},
    )
    engine = DoclingEngine(spec)
    engine.prepare()

    doc = DocumentInput(
        document_id="test_docling_pdf",
        path="datasets/documents/sample_invoice.pdf",
        filename="sample_invoice.pdf",
        sha256="dummy",
        page_count=1,
    )
    res = engine.extract(doc)
    assert res.success is True
    assert "LOGISTICS" in res.full_text or "0101234567" in res.full_text or "1K24TAA" in res.full_text
    engine.close()
