"""Contract test for PPStructureEngine adapter."""

from document_benchmark.core.contracts import DocumentInput, EngineSpec
from document_benchmark.core.statuses import EngineStatus
from document_benchmark.engines.ppstructure_engine import PPStructureEngine, _check_ppstructure_import


def test_ppstructure_engine_healthcheck():
    spec = EngineSpec(
        engine_id="ppstructure_v3",
        config_id="ppstructure_vi_table_cpu",
        options={
            "language": "vi",
            "use_general_ocr": True,
            "use_table_recognition": True,
            "use_formula_recognition": False,
            "use_seal_recognition": False,
        },
    )
    engine = PPStructureEngine(spec)
    health = engine.healthcheck()

    is_installed, _, _missing = _check_ppstructure_import()
    if is_installed:
        assert health.available is True
        assert health.status == EngineStatus.SUCCESS
    else:
        assert health.available is False
        assert health.status == EngineStatus.UNAVAILABLE
        assert len(health.missing_dependencies) > 0


def test_ppstructure_engine_extraction():
    is_installed, _, _ = _check_ppstructure_import()
    if not is_installed:
        return

    spec = EngineSpec(
        engine_id="ppstructure_v3",
        config_id="ppstructure_vi_table_cpu",
        options={"language": "vi", "use_general_ocr": True, "use_table_recognition": True},
    )
    engine = PPStructureEngine(spec)
    engine.prepare()

    doc = DocumentInput(
        document_id="test_ppstructure_pdf",
        path="datasets/documents/sample_invoice.pdf",
        filename="sample_invoice.pdf",
        sha256="dummy",
        page_count=1,
    )
    res = engine.extract(doc)
    assert res.success is True
    assert res.engine_id == "ppstructure_v3"
    engine.close()
