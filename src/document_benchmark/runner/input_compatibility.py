"""Compatibility checks that keep benchmark tracks comparable."""

from __future__ import annotations

from dataclasses import dataclass

from document_benchmark.core.contracts import DocumentInput, EngineSpec


@dataclass(frozen=True)
class CompatibilityDecision:
    supported: bool
    input_profile: str | None
    engine_track: str | None
    reason: str | None = None


def infer_input_profile(document: DocumentInput) -> str | None:
    explicit = document.metadata.get("input_profile")
    if explicit:
        return str(explicit)
    if document.metadata.get("is_image_only_pdf") is True:
        return "scan_ocr"
    if document.metadata.get("has_text_layer") is True:
        return "native_pdf"
    return None


def assess_input_compatibility(
    engine_spec: EngineSpec,
    document: DocumentInput,
) -> CompatibilityDecision:
    """Reject known-invalid engine/document pairings before model loading."""
    input_profile = infer_input_profile(document)
    engine_track_value = engine_spec.options.get("benchmark_track")
    engine_track = str(engine_track_value) if engine_track_value else None

    if input_profile == "scan_ocr" and not engine_spec.supports_scanned_pdf:
        return CompatibilityDecision(
            supported=False,
            input_profile=input_profile,
            engine_track=engine_track,
            reason=(
                f"Config '{engine_spec.config_id}' does not support scanned/image-only PDFs"
            ),
        )
    if input_profile == "native_pdf" and not engine_spec.supports_pdf_text:
        return CompatibilityDecision(
            supported=False,
            input_profile=input_profile,
            engine_track=engine_track,
            reason=f"Config '{engine_spec.config_id}' does not support native text PDFs",
        )
    if input_profile and engine_track and input_profile != engine_track:
        return CompatibilityDecision(
            supported=False,
            input_profile=input_profile,
            engine_track=engine_track,
            reason=(
                f"Benchmark track mismatch: document={input_profile}, config={engine_track}"
            ),
        )
    return CompatibilityDecision(
        supported=True,
        input_profile=input_profile,
        engine_track=engine_track,
    )
