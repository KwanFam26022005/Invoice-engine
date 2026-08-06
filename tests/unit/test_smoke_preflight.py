"""Tests for no-model-load smoke preflight checks."""

from __future__ import annotations

from document_benchmark.core.contracts import EngineHealth, EngineSpec
from document_benchmark.core.engine_registry import EngineRegistry
from document_benchmark.core.statuses import EngineStatus
from document_benchmark.engines.mock_engine import MockEngine
from document_benchmark.smoke import preflight


class HealthyRegistry(EngineRegistry):
    def healthcheck_config(self, config_id: str) -> EngineHealth:
        spec = self.get_config(config_id)
        assert spec is not None
        return EngineHealth(
            engine_id=spec.engine_id,
            config_id=config_id,
            status=EngineStatus.SUCCESS,
            available=True,
            runtime_metadata={"engine_generation": "test"},
        )


def test_mock_preflight_is_ready_without_loading_model() -> None:
    engine_registry = HealthyRegistry()
    engine_registry.register_engine_class("mock", MockEngine)
    engine_registry.register_config(
        EngineSpec(
            engine_id="mock",
            config_id="mock_smoke",
            options={"benchmark_track": "scan_ocr"},
        )
    )

    result = preflight.run_engine_preflight(
        "mock_smoke", engine_registry=engine_registry
    )

    assert result.ready is True
    assert result.model_loaded is False
    assert result.benchmark_track == "scan_ocr"


def test_ppstructure_v3_preflight_requires_major_three(monkeypatch) -> None:
    engine_registry = HealthyRegistry()
    engine_registry.register_config(
        EngineSpec(
            engine_id="ppstructure_v3",
            config_id="ppv3",
            supports_scanned_pdf=True,
            options={"benchmark_track": "scan_ocr"},
        )
    )

    versions = {
        "paddleocr": "2.9.1",
        "paddlepaddle": "2.6.2",
        "docling": None,
        "docling-core": None,
        "easyocr": None,
    }
    monkeypatch.setattr(preflight, "package_version", lambda name: versions[name])
    monkeypatch.setattr(preflight, "_has_symbol", lambda *_args: False)

    result = preflight.run_engine_preflight("ppv3", engine_registry=engine_registry)

    assert result.ready is False
    assert "PaddleOCR 3.x is required" in result.reasons
    assert "PaddlePaddle 3.x is required" in result.reasons
    assert result.model_loaded is False


def test_docling_ocr_preflight_requires_vietnamese_and_easyocr(monkeypatch) -> None:
    engine_registry = HealthyRegistry()
    engine_registry.register_config(
        EngineSpec(
            engine_id="docling",
            config_id="docling_scan",
            supports_scanned_pdf=True,
            options={
                "benchmark_track": "scan_ocr",
                "do_ocr": True,
                "ocr_languages": ["en"],
            },
        )
    )

    versions = {
        "docling": "2.118.0",
        "docling-core": "2.90.0",
        "easyocr": None,
        "paddleocr": None,
        "paddlepaddle": None,
    }
    monkeypatch.setattr(preflight, "package_version", lambda name: versions[name])

    result = preflight.run_engine_preflight(
        "docling_scan", engine_registry=engine_registry
    )

    assert result.ready is False
    assert "EasyOCR is required for this Docling OCR profile" in result.reasons
    assert "Vietnamese OCR language 'vi' is required" in result.reasons
