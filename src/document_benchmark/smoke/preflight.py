"""Environment-only preflight checks for smoke benchmark engine profiles."""

from __future__ import annotations

from datetime import datetime, timezone
import importlib
import platform
import sys
from typing import Any

from pydantic import BaseModel, Field

from document_benchmark.core.engine_registry import EngineRegistry, registry
from document_benchmark.engines.runtime import package_version


class EnginePreflightResult(BaseModel):
    """Serializable result of a no-model-load environment preflight."""

    config_id: str
    engine_id: str
    ready: bool
    checked_at: str
    python_version: str
    python_executable: str
    platform: str
    benchmark_track: str | None = None
    health_status: str
    reasons: list[str] = Field(default_factory=list)
    package_versions: dict[str, str | None] = Field(default_factory=dict)
    runtime_metadata: dict[str, Any] = Field(default_factory=dict)
    model_loaded: bool = False


def _major(version: str | None) -> int | None:
    if not version:
        return None
    first = version.split(".", 1)[0]
    return int(first) if first.isdigit() else None


def _has_symbol(module_name: str, symbol: str) -> bool:
    try:
        module = importlib.import_module(module_name)
    except Exception:
        return False
    return hasattr(module, symbol)


def run_engine_preflight(
    config_id: str,
    *,
    engine_registry: EngineRegistry = registry,
) -> EnginePreflightResult:
    """Check package identity and adapter health without calling ``prepare``."""

    spec = engine_registry.get_config(config_id)
    checked_at = datetime.now(timezone.utc).isoformat()
    if spec is None:
        return EnginePreflightResult(
            config_id=config_id,
            engine_id="unknown",
            ready=False,
            checked_at=checked_at,
            python_version=platform.python_version(),
            python_executable=sys.executable,
            platform=platform.platform(),
            health_status="UNAVAILABLE",
            reasons=["Engine configuration is not registered"],
        )

    package_versions = {
        "docling": package_version("docling"),
        "docling-core": package_version("docling-core"),
        "easyocr": package_version("easyocr"),
        "paddleocr": package_version("paddleocr"),
        "paddlepaddle": package_version("paddlepaddle"),
    }
    health = engine_registry.healthcheck_config(config_id)
    reasons: list[str] = []
    if not spec.enabled:
        reasons.append("Engine profile is disabled")
    if not health.available:
        reasons.append(health.error_message or "Engine healthcheck reported unavailable")

    if spec.engine_id == "docling":
        if _major(package_versions["docling"]) != 2:
            reasons.append("Docling 2.x is required")
        if bool(spec.options.get("do_ocr")):
            if package_versions["easyocr"] is None:
                reasons.append("EasyOCR is required for this Docling OCR profile")
            languages = [str(value) for value in spec.options.get("ocr_languages", [])]
            if "vi" not in languages:
                reasons.append("Vietnamese OCR language 'vi' is required")

    if spec.engine_id == "ppstructure_v3":
        if _major(package_versions["paddleocr"]) != 3:
            reasons.append("PaddleOCR 3.x is required")
        if _major(package_versions["paddlepaddle"]) != 3:
            reasons.append("PaddlePaddle 3.x is required")
        if package_versions["paddleocr"] and not _has_symbol("paddleocr", "PPStructureV3"):
            reasons.append("Installed paddleocr does not expose PPStructureV3")

    ready = spec.enabled and health.available and not reasons
    return EnginePreflightResult(
        config_id=config_id,
        engine_id=spec.engine_id,
        ready=ready,
        checked_at=checked_at,
        python_version=platform.python_version(),
        python_executable=sys.executable,
        platform=platform.platform(),
        benchmark_track=spec.options.get("benchmark_track"),
        health_status=health.status.value,
        reasons=reasons,
        package_versions=package_versions,
        runtime_metadata=health.runtime_metadata,
        model_loaded=False,
    )


def inspect_paddle3_environment() -> dict[str, Any]:
    """Return a standalone PaddleOCR 3.x environment report."""

    paddle_version = package_version("paddlepaddle")
    paddleocr_version = package_version("paddleocr")
    has_v3 = bool(paddleocr_version) and _has_symbol("paddleocr", "PPStructureV3")
    reasons: list[str] = []
    if _major(paddle_version) != 3:
        reasons.append("PaddlePaddle major version must be 3")
    if _major(paddleocr_version) != 3:
        reasons.append("PaddleOCR major version must be 3")
    if paddleocr_version and not has_v3:
        reasons.append("PPStructureV3 public symbol is missing")
    return {
        "ready": not reasons,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "python_version": platform.python_version(),
        "python_executable": sys.executable,
        "platform": platform.platform(),
        "paddlepaddle_version": paddle_version,
        "paddleocr_version": paddleocr_version,
        "has_ppstructure_v3": has_v3,
        "reasons": reasons,
        "model_loaded": False,
    }
