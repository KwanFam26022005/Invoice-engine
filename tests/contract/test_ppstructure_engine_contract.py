"""Contract tests for genuine PP-StructureV3 and explicit V2 legacy adapters."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from document_benchmark.core.contracts import DocumentInput, EngineSpec
from document_benchmark.core.statuses import EngineStatus
from document_benchmark.engines.ppstructure_engine import (
    PPStructureV3Engine,
    _check_ppstructure_v3_import,
)
from document_benchmark.engines.ppstructure_v2_engine import (
    PPStructureV2LegacyEngine,
    _check_ppstructure_v2_import,
)


def test_ppstructure_v3_healthcheck() -> None:
    spec = EngineSpec(
        engine_id="ppstructure_v3",
        config_id="ppstructure_v3_vi_table_cpu",
        supports_scanned_pdf=True,
        options={
            "benchmark_track": "scan_ocr",
            "language": "vi",
            "use_table_recognition": True,
            "use_formula_recognition": False,
        },
    )
    engine = PPStructureV3Engine(spec)
    health = engine.healthcheck()
    is_installed, _, _ = _check_ppstructure_v3_import()

    assert health.available is is_installed
    assert health.runtime_metadata["engine_generation"] == "PP-StructureV3"
    if is_installed:
        assert health.status == EngineStatus.SUCCESS
    else:
        assert health.status == EngineStatus.UNAVAILABLE
        assert health.missing_dependencies


def test_ppstructure_v2_legacy_is_explicitly_labelled() -> None:
    spec = EngineSpec(
        engine_id="ppstructure_v2_legacy",
        config_id="ppstructure_v2_legacy_vi_table_cpu",
        enabled=True,
        supports_scanned_pdf=True,
        options={"benchmark_track": "scan_ocr"},
    )
    engine = PPStructureV2LegacyEngine(spec)
    metadata = engine._runtime_metadata()
    assert metadata["engine_generation"] == "PP-StructureV2 legacy"
    is_installed, _, _ = _check_ppstructure_v2_import()
    assert engine.healthcheck().available is is_installed


@pytest.mark.optional_engine
def test_ppstructure_v3_extraction(tmp_path: Path) -> None:
    if os.getenv("RUN_OPTIONAL_ENGINE_TESTS") != "1":
        pytest.skip("Set RUN_OPTIONAL_ENGINE_TESTS=1 to run PP-StructureV3 model extraction")
    pytest.importorskip("paddle")
    paddleocr = pytest.importorskip("paddleocr")
    if not hasattr(paddleocr, "PPStructureV3"):
        pytest.skip("Installed PaddleOCR does not expose PPStructureV3")
    fitz = pytest.importorskip("fitz")

    pdf_path = tmp_path / "ppstructure_scan_fixture.pdf"
    with fitz.open() as document:
        page = document.new_page()
        page.insert_text((50, 50), "Invoice No: INV-0002 Total: 2,200,000")
        pixmap = page.get_pixmap()
        image_pdf = fitz.open()
        image_page = image_pdf.new_page(width=page.rect.width, height=page.rect.height)
        image_page.insert_image(image_page.rect, pixmap=pixmap)
        image_pdf.save(pdf_path)
        image_pdf.close()

    spec = EngineSpec(
        engine_id="ppstructure_v3",
        config_id="ppstructure_v3_vi_table_cpu",
        supports_scanned_pdf=True,
        options={
            "benchmark_track": "scan_ocr",
            "language": "vi",
            "use_doc_orientation_classify": False,
            "use_doc_unwarping": False,
            "use_textline_orientation": False,
            "use_table_recognition": True,
            "use_formula_recognition": False,
            "use_chart_recognition": False,
            "use_seal_recognition": False,
        },
    )
    engine = PPStructureV3Engine(spec)
    engine.prepare()
    try:
        result = engine.extract(
            DocumentInput(
                document_id="test_ppstructure_v3_pdf",
                path=str(pdf_path),
                filename=pdf_path.name,
                sha256="fixture",
                page_count=1,
                metadata={"is_image_only_pdf": True, "input_profile": "scan_ocr"},
            )
        )
    finally:
        engine.close()

    assert result.success is True
    assert result.engine_id == "ppstructure_v3"
    assert result.raw_payload["runtime_metadata"]["engine_generation"] == "PP-StructureV3"
    assert result.pages
