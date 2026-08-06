"""Contract tests for the Docling adapter."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from document_benchmark.core.contracts import DocumentInput, EngineSpec
from document_benchmark.core.statuses import EngineStatus
from document_benchmark.engines.docling_engine import DoclingEngine, _check_docling_import


def test_docling_engine_healthcheck() -> None:
    spec = EngineSpec(
        engine_id="docling",
        config_id="docling_text_only_cpu",
        supports_scanned_pdf=False,
        options={
            "benchmark_track": "native_pdf",
            "do_ocr": False,
            "do_table_structure": False,
        },
    )
    engine = DoclingEngine(spec)
    health = engine.healthcheck()

    is_installed, _, _ = _check_docling_import()
    if is_installed:
        assert health.available is True
        assert health.status == EngineStatus.SUCCESS
        assert health.runtime_metadata["engine_generation"] == "Docling"
    else:
        assert health.available is False
        assert health.status == EngineStatus.UNAVAILABLE
        assert "docling" in health.missing_dependencies


def test_docling_ocr_profile_metadata() -> None:
    spec = EngineSpec(
        engine_id="docling",
        config_id="docling_ocr_easyocr_vi_cpu",
        supports_scanned_pdf=True,
        options={
            "benchmark_track": "scan_ocr",
            "do_ocr": True,
            "ocr_engine": "easyocr",
            "ocr_languages": ["vi", "en"],
        },
    )
    engine = DoclingEngine(spec)
    metadata = engine._runtime_metadata()
    assert metadata["ocr_enabled"] is True
    assert metadata["ocr_engine"] == "easyocr"
    assert metadata["ocr_languages"] == ["vi", "en"]
    assert metadata["benchmark_track"] == "scan_ocr"


@pytest.mark.optional_engine
def test_docling_engine_extraction(tmp_path: Path) -> None:
    if os.getenv("RUN_OPTIONAL_ENGINE_TESTS") != "1":
        pytest.skip("Set RUN_OPTIONAL_ENGINE_TESTS=1 to run Docling model extraction")
    pytest.importorskip("docling")
    fitz = pytest.importorskip("fitz")

    pdf_path = tmp_path / "docling_text_fixture.pdf"
    with fitz.open() as document:
        page = document.new_page()
        page.insert_text((50, 50), "Invoice No: INV-0001 Total: 1,100,000")
        document.save(pdf_path)

    spec = EngineSpec(
        engine_id="docling",
        config_id="docling_text_only_cpu",
        supports_scanned_pdf=False,
        options={
            "benchmark_track": "native_pdf",
            "do_ocr": False,
            "do_table_structure": False,
        },
    )
    engine = DoclingEngine(spec)
    engine.prepare()
    try:
        result = engine.extract(
            DocumentInput(
                document_id="test_docling_pdf",
                path=str(pdf_path),
                filename=pdf_path.name,
                sha256="fixture",
                page_count=1,
                metadata={"has_text_layer": True, "input_profile": "native_pdf"},
            )
        )
    finally:
        engine.close()

    assert result.success is True
    assert "INV-0001" in result.full_text
    assert result.raw_payload["runtime_metadata"]["engine_generation"] == "Docling"
