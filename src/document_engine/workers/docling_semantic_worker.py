"""Isolated local worker for Docling structured semantic extraction."""

import importlib
import importlib.util
import json
import os
from pathlib import Path
import sys


WEIGHT_SUFFIXES = {".safetensors", ".bin", ".pt", ".onnx"}
DEFAULT_MODEL_REPO_ID = "numind/NuExtract-2.0-2B"
DEFAULT_MODEL_REVISION = "fe5b2f0b63b81150721435a3ca1129a75c59c74e"


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
        "docling.datamodel.accelerator_options",
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
    has_weight = False
    has_config = False
    try:
        for item in path.rglob("*"):
            if not item.is_file():
                continue
            if item.suffix.lower() in WEIGHT_SUFFIXES:
                has_weight = True
            if item.name == "config.json":
                has_config = True
            if has_weight and has_config:
                return True
    except OSError:
        return False
    return False


def _truthy(value: object, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def semantic_runtime_config(options: dict | None = None) -> dict:
    """Resolve a local runtime config without loading the semantic model."""
    options = options or {}
    torch_module = None
    cuda_available = False
    if importlib.util.find_spec("torch") is not None:
        try:
            torch_module = importlib.import_module("torch")
            cuda_available = bool(torch_module.cuda.is_available())
        except Exception:
            torch_module = None

    requested_device = str(
        options.get("device")
        or os.getenv("DOCLING_SEMANTIC_DEVICE")
        or "auto"
    ).strip().lower()
    if requested_device not in {"auto", "cpu", "cuda"}:
        return {
            "requested_device": requested_device,
            "actual_device": requested_device,
            "cuda_available": cuda_available,
            "resource_ready": False,
            "resource_error": "UNSUPPORTED_SEMANTIC_DEVICE",
            "num_threads": 1,
            "load_in_8bit": False,
            "torch_dtype": "bfloat16",
            "model_repo_id": DEFAULT_MODEL_REPO_ID,
            "model_revision": DEFAULT_MODEL_REVISION,
        }

    actual_device = requested_device
    if requested_device == "auto":
        actual_device = "cuda" if cuda_available else "cpu"

    resource_ready = not (actual_device == "cuda" and not cuda_available)
    resource_error = None if resource_ready else "CUDA_UNAVAILABLE"

    default_threads = os.cpu_count() or 4
    raw_threads = options.get("num_threads") or os.getenv("DOCLING_SEMANTIC_NUM_THREADS")
    try:
        num_threads = max(1, int(raw_threads)) if raw_threads else max(1, min(default_threads, 8))
    except (TypeError, ValueError):
        num_threads = max(1, min(default_threads, 8))

    requested_8bit = _truthy(
        options.get("load_in_8bit", os.getenv("DOCLING_SEMANTIC_LOAD_IN_8BIT")),
        default=True,
    )
    load_in_8bit = bool(actual_device == "cuda" and requested_8bit)

    torch_dtype = str(
        options.get("torch_dtype")
        or os.getenv("DOCLING_SEMANTIC_TORCH_DTYPE")
        or "bfloat16"
    )

    return {
        "requested_device": requested_device,
        "actual_device": actual_device,
        "cuda_available": cuda_available,
        "resource_ready": resource_ready,
        "resource_error": resource_error,
        "num_threads": num_threads,
        "load_in_8bit": load_in_8bit,
        "torch_dtype": torch_dtype,
        "model_repo_id": str(options.get("model_repo_id") or DEFAULT_MODEL_REPO_ID),
        "model_revision": str(options.get("model_revision") or DEFAULT_MODEL_REVISION),
    }


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
    runtime_config = semantic_runtime_config(options)

    if operation == "healthcheck":
        offline_ready = (
            api_ok
            and cache_ok
            and runtime_config["resource_ready"]
        )
        response = {
            "request_id": req_id,
            "success": offline_ready or (
                api_ok and runtime_config["resource_ready"] and allow_model_download
            ),
            "actual_parser_id": "docling_semantic",
            "actual_parser_version": versions.get("docling", "unknown"),
            "runtime_versions": versions,
            "health_data": {
                "api_available": api_ok,
                "api_error": api_error,
                "artifacts_configured": model_path is not None,
                "model_cache_ready": cache_ok,
                "offline_runtime_ready": offline_ready,
                "download_allowed": allow_model_download,
                "requested_device": runtime_config["requested_device"],
                "actual_device": runtime_config["actual_device"],
                "cuda_available": runtime_config["cuda_available"],
                "resource_ready": runtime_config["resource_ready"],
                "resource_error": runtime_config["resource_error"],
                "num_threads": runtime_config["num_threads"],
                "load_in_8bit": runtime_config["load_in_8bit"],
                "torch_dtype": runtime_config["torch_dtype"],
                "model_repo_id": runtime_config["model_repo_id"],
                "model_revision": runtime_config["model_revision"],
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
    if not runtime_config["resource_ready"]:
        print(
            json.dumps(
                safe_error_response(
                    req_id,
                    runtime_config["resource_error"] or "SEMANTIC_RESOURCE_UNAVAILABLE",
                    versions,
                )
            ),
            flush=True,
        )
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
        from docling.datamodel.accelerator_options import AcceleratorOptions
        from docling.datamodel.base_models import InputFormat
        from docling.datamodel.pipeline_options import VlmExtractionPipelineOptions
        from docling.document_extractor import DocumentExtractor, ExtractionFormatOption
        from docling.pipeline.extraction_vlm_pipeline import ExtractionVlmPipeline

        accelerator_options = AcceleratorOptions(
            device=runtime_config["actual_device"],
            num_threads=runtime_config["num_threads"],
        )
        default_pipeline_options = VlmExtractionPipelineOptions()
        vlm_options = default_pipeline_options.vlm_options.model_copy(
            update={
                "repo_id": runtime_config["model_repo_id"],
                "revision": runtime_config["model_revision"],
                "load_in_8bit": runtime_config["load_in_8bit"],
                "torch_dtype": runtime_config["torch_dtype"],
                "trust_remote_code": False,
            }
        )
        pipeline_options = VlmExtractionPipelineOptions(
            enable_remote_services=False,
            allow_external_plugins=False,
            artifacts_path=str(model_path) if model_path else None,
            accelerator_options=accelerator_options,
            vlm_options=vlm_options,
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
            errors = getattr(page, "errors", None) or []
            if errors:
                page_errors += 1
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
                "device": runtime_config["actual_device"],
                "load_in_8bit": runtime_config["load_in_8bit"],
                "model_repo_id": runtime_config["model_repo_id"],
                "model_revision": runtime_config["model_revision"],
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
                safe_error_response(
                    req_id,
                    f"DOCLING_SEMANTIC_{type(exc).__name__.upper()}",
                    versions,
                )
            ),
            flush=True,
        )


if __name__ == "__main__":
    main()
