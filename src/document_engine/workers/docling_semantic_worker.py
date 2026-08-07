"""Isolated local worker for Docling structured semantic extraction."""

import importlib
import importlib.util
import json
import os
from pathlib import Path
import sys


WEIGHT_SUFFIXES = {".safetensors", ".bin", ".pt", ".onnx"}


def runtime_versions() -> dict:
    versions = {"python": sys.version.split()[0]}
    for pkg in ("docling", "docling_core", "torch", "transformers", "pydantic"):
        try:
            mod = importlib.import_module(pkg)
            versions[pkg] = getattr(mod, "__version__", "installed")
        except Exception:
            pass
    return versions


def api_available() -> tuple[bool, str | None]:
    required = (
        "docling.document_extractor",
        "docling.datamodel.base_models",
        "docling.datamodel.pipeline_options",
        "docling.pipeline.extraction_vlm_pipeline",
        "docling.backend.pypdfium2_backend",
    )
    for module in required:
        if importlib.util.find_spec(module) is None:
            return False, module
    try:
        from docling.document_extractor import DocumentExtractor, ExtractionFormatOption
        from docling.datamodel.pipeline_options import VlmExtractionPipelineOptions

        _ = DocumentExtractor, ExtractionFormatOption, VlmExtractionPipelineOptions
    except Exception as exc:
        return False, type(exc).__name__
    return True, None


def artifacts_path(options: dict) -> Path | None:
    raw = options.get("artifacts_path") or os.getenv("DOCLING_SEMANTIC_ARTIFACTS_PATH")
    if not raw:
        return None
    return Path(raw).expanduser().resolve()


def artifacts_ready(path: Path | None) -> bool:
    if path is None or not path.is_dir():
        return False
    try:
        return any(item.is_file() and item.suffix.lower() in WEIGHT_SUFFIXES for item in path.rglob("*"))
    except OSError:
        return False


def flatten(data, prefix=""):
    values = []
    abstained = []
    if isinstance(data, dict):
        for key, value in data.items():
            child = f"{prefix}.{key}" if prefix else str(key)
            child_values, child_abstained = flatten(value, child)
            values.extend(child_values)
            abstained.extend(child_abstained)
        return values, abstained
    if isinstance(data, list):
        for index, value in enumerate(data):
            child_values, child_abstained = flatten(value, f"{prefix}[{index}]")
            values.extend(child_values)
            abstained.extend(child_abstained)
        return values, abstained
    if prefix:
        if data is None:
            abstained.append(prefix)
        else:
            values.append((prefix, data))
    return values, abstained


def safe_error_response(req_id: str, code: str, versions: dict) -> dict:
    return {
        "request_id": req_id,
        "success": False,
        "actual_parser_id": "docling_semantic",
        "actual_parser_version": versions.get("docling", "unknown"),
        "runtime_versions": versions,
        "error_type": code,
        "error_message": code,
    }


def main() -> None:
    raw_input = sys.stdin.read()
    if not raw_input.strip():
        sys.exit(1)

    request = json.loads(raw_input)
    req_id = request.get("request_id", "req_unknown")
    operation = request.get("operation", "healthcheck")
    options = request.get("options", {}) or {}
    allow_model_download = bool(request.get("allow_model_download", False))
    versions = runtime_versions()

    if not allow_model_download:
        os.environ.setdefault("HF_HUB_OFFLINE", "1")
        os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

    api_ok, api_error = api_available()
    model_path = artifacts_path(options)
    cache_ok = artifacts_ready(model_path)

    if operation == "healthcheck":
        response = {
            "request_id": req_id,
            "success": api_ok and (cache_ok or allow_model_download),
            "actual_parser_id": "docling_semantic",
            "actual_parser_version": versions.get("docling", "unknown"),
            "runtime_versions": versions,
            "health_data": {
                "api_available": api_ok,
                "api_error": api_error,
                "artifacts_configured": model_path is not None,
                "model_cache_ready": cache_ok,
                "offline_runtime_ready": api_ok and cache_ok,
                "download_allowed": allow_model_download,
                "cuda_available": bool(
                    importlib.util.find_spec("torch")
                    and importlib.import_module("torch").cuda.is_available()
                ),
            },
        }
        print(json.dumps(response), flush=True)
        return

    if operation != "extract":
        print(json.dumps(safe_error_response(req_id, "UNSUPPORTED_WORKER_OPERATION", versions)), flush=True)
        return
    if not api_ok:
        print(json.dumps(safe_error_response(req_id, "DOCLING_SEMANTIC_API_UNAVAILABLE", versions)), flush=True)
        return
    if not allow_model_download and not cache_ok:
        print(json.dumps(safe_error_response(req_id, "DOCLING_SEMANTIC_CACHE_NOT_READY", versions)), flush=True)
        return

    input_path = Path(request.get("input_path", ""))
    if not input_path.is_file() or input_path.suffix.lower() != ".pdf":
        print(json.dumps(safe_error_response(req_id, "INVALID_SEMANTIC_INPUT", versions)), flush=True)
        return

    template = options.get("template")
    family = options.get("family")
    schema_name = options.get("schema_name")
    if not isinstance(template, dict) or not family or not schema_name:
        print(json.dumps(safe_error_response(req_id, "INVALID_SEMANTIC_TEMPLATE", versions)), flush=True)
        return

    try:
        from docling.backend.pypdfium2_backend import PyPdfiumDocumentBackend
        from docling.datamodel.base_models import InputFormat
        from docling.datamodel.pipeline_options import VlmExtractionPipelineOptions
        from docling.document_extractor import DocumentExtractor, ExtractionFormatOption
        from docling.pipeline.extraction_vlm_pipeline import ExtractionVlmPipeline

        pipeline_options = VlmExtractionPipelineOptions(
            enable_remote_services=False,
            allow_external_plugins=False,
            artifacts_path=str(model_path) if model_path else None,
        )
        format_option = ExtractionFormatOption(
            pipeline_cls=ExtractionVlmPipeline,
            backend=PyPdfiumDocumentBackend,
            pipeline_options=pipeline_options,
        )
        extractor = DocumentExtractor(
            allowed_formats=[InputFormat.PDF],
            extraction_format_options={InputFormat.PDF: format_option},
        )
        result = extractor.extract(
            source=input_path,
            template=template,
            raises_on_error=False,
        )

        candidates = []
        abstained_fields = []
        page_errors = 0
        for page in getattr(result, "pages", []) or []:
            page_no = int(getattr(page, "page_no", 1))
            data = getattr(page, "extracted_data", None)
            if not isinstance(data, dict):
                page_errors += 1
                continue
            atomic_values, abstained = flatten(data)
            abstained_fields.extend(abstained)
            for field_path, value in atomic_values:
                candidates.append(
                    {
                        "field_path": field_path,
                        "value": value,
                        "raw_value": value,
                        "confidence": None,
                        "source_method": "docling_semantic",
                        "status": "proposed",
                        "evidence_hints": [{"page_number": page_no}],
                        "warnings": [],
                    }
                )

        semantic_result = {
            "extractor_id": "docling_semantic",
            "extractor_version": versions.get("docling", "unknown"),
            "document_id": request.get("document_id", ""),
            "family": family,
            "success": True,
            "candidates": candidates,
            "abstained_fields": sorted(set(abstained_fields)),
            "warnings": ["PAGE_EXTRACTION_ERROR"] if page_errors else [],
            "metadata": {
                "schema_name": schema_name,
                "page_count": len(getattr(result, "pages", []) or []),
                "candidate_count": len(candidates),
                "remote_services_enabled": False,
            },
        }
        response = {
            "request_id": req_id,
            "success": True,
            "actual_parser_id": "docling_semantic",
            "actual_parser_version": versions.get("docling", "unknown"),
            "runtime_versions": versions,
            "semantic_result_dict": semantic_result,
        }
        print(json.dumps(response), flush=True)
    except Exception as exc:
        print(
            json.dumps(
                safe_error_response(req_id, f"DOCLING_SEMANTIC_{type(exc).__name__.upper()}", versions)
            ),
            flush=True,
        )


if __name__ == "__main__":
    main()
