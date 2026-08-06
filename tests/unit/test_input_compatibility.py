"""Tests for fair benchmark-track routing."""

from document_benchmark.core.contracts import DocumentInput, EngineSpec
from document_benchmark.runner.input_compatibility import assess_input_compatibility


def make_document(profile: str) -> DocumentInput:
    return DocumentInput(
        document_id=f"doc_{profile}",
        path="fixture.pdf",
        filename="fixture.pdf",
        sha256="fixture",
        metadata={
            "input_profile": profile,
            "is_image_only_pdf": profile == "scan_ocr",
            "has_text_layer": profile == "native_pdf",
        },
    )


def test_native_docling_profile_rejects_scanned_pdf() -> None:
    spec = EngineSpec(
        engine_id="docling",
        config_id="docling_text_only_cpu",
        supports_pdf_text=True,
        supports_scanned_pdf=False,
        options={"benchmark_track": "native_pdf"},
    )
    decision = assess_input_compatibility(spec, make_document("scan_ocr"))
    assert decision.supported is False
    assert "does not support scanned" in (decision.reason or "")


def test_ocr_profile_accepts_scanned_pdf() -> None:
    spec = EngineSpec(
        engine_id="docling",
        config_id="docling_ocr_easyocr_vi_cpu",
        supports_pdf_text=True,
        supports_scanned_pdf=True,
        options={"benchmark_track": "scan_ocr"},
    )
    decision = assess_input_compatibility(spec, make_document("scan_ocr"))
    assert decision.supported is True


def test_track_mismatch_is_rejected_even_when_capability_is_broad() -> None:
    spec = EngineSpec(
        engine_id="ppstructure_v3",
        config_id="ppstructure_v3_vi_table_cpu",
        supports_pdf_text=True,
        supports_scanned_pdf=True,
        options={"benchmark_track": "scan_ocr"},
    )
    decision = assess_input_compatibility(spec, make_document("native_pdf"))
    assert decision.supported is False
    assert "track mismatch" in (decision.reason or "").casefold()


def test_unknown_input_profile_is_not_guessed() -> None:
    document = DocumentInput(
        document_id="unknown",
        path="fixture.pdf",
        filename="fixture.pdf",
        sha256="fixture",
    )
    spec = EngineSpec(
        engine_id="mock",
        config_id="mock_default",
        supports_pdf_text=True,
        supports_scanned_pdf=True,
    )
    decision = assess_input_compatibility(spec, document)
    assert decision.supported is True
    assert decision.input_profile is None
