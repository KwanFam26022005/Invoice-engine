"""Standalone worker process for running PaddleOCR-VL visual/layout parsing."""

import importlib
import importlib.util
import json
import logging
import os
from pathlib import Path
import sys
import time

logging.basicConfig(level=logging.INFO, stream=sys.stderr)
logger = logging.getLogger("paddleocr_vl_worker")


_WEIGHT_EXTENSIONS = frozenset({".pdiparams", ".safetensors", ".bin", ".onnx"})
_LOCAL_VL_BACKEND = "native"


def get_runtime_versions() -> dict:
    versions = {"python": sys.version.split()[0]}
    for pkg in ("paddle", "paddleocr", "pydantic"):
        try:
            mod = importlib.import_module(pkg)
            versions[pkg] = getattr(mod, "__version__", "installed")
        except Exception:
            pass
    return versions


def has_model_artifacts(path: Path) -> bool:
    """Return True only when a model directory contains recognized weights."""
    if not path.is_dir():
        return False
    try:
        return any(
            item.is_file() and item.suffix.lower() in _WEIGHT_EXTENSIONS
            for item in path.rglob("*")
        )
    except OSError:
        return False


def check_model_cache_status(options: dict) -> tuple[str, bool]:
    """Inspect explicit local model directories without loading a model."""
    layout_dir = options.get("layout_detection_model_dir")
    vl_rec_dir = options.get("vl_rec_model_dir")

    if layout_dir or vl_rec_dir:
        if not layout_dir or not vl_rec_dir:
            return "LOCAL_MODEL_DIRS_INVALID", False

        p_layout = Path(layout_dir)
        p_vl = Path(vl_rec_dir)
        if not (p_layout.is_dir() and p_vl.is_dir()):
            return "LOCAL_MODEL_DIRS_INVALID", False

        if has_model_artifacts(p_layout) and has_model_artifacts(p_vl):
            return "READY_LOCAL_MODEL_DIRS", True
        return "LOCAL_MODEL_DIRS_PARTIALLY_VERIFIED", False

    # A generic framework cache is not enough to prove both exact Phase 9E models.
    user_home = Path.home()
    paddle_cache = user_home / ".paddleocr"
    paddlex_cache = user_home / ".paddlex" / "official_models"
    has_cached_weights = False
    for cache_root in (paddle_cache, paddlex_cache):
        if cache_root.exists() and has_model_artifacts(cache_root):
            has_cached_weights = True
            break
    if has_cached_weights:
        return "MODEL_CACHE_PARTIALLY_VERIFIED", False
    return "CACHE_MISSING", False


def create_paddleocr_vl_pipeline(options: dict):
    """Instantiate PaddleOCRVL using the current local direct-inference API."""
    from paddleocr import PaddleOCRVL

    kwargs = {
        "pipeline_version": options.get("pipeline_version", "v1.6"),
        "device": options.get("device", "cpu"),
        "vl_rec_backend": options.get("vl_rec_backend", _LOCAL_VL_BACKEND),
        "use_doc_orientation_classify": options.get(
            "use_doc_orientation_classify", False
        ),
        "use_doc_unwarping": options.get("use_doc_unwarping", False),
        "use_layout_detection": options.get("use_layout_detection", True),
        "use_chart_recognition": options.get("use_chart_recognition", False),
        "use_seal_recognition": options.get("use_seal_recognition", False),
        "use_ocr_for_image_block": options.get("use_ocr_for_image_block", False),
        "use_queues": options.get("use_queues", False),
    }

    layout_dir = options.get("layout_detection_model_dir")
    vl_rec_dir = options.get("vl_rec_model_dir")
    if layout_dir:
        kwargs["layout_detection_model_dir"] = layout_dir
    if vl_rec_dir:
        kwargs["vl_rec_model_dir"] = vl_rec_dir

    return PaddleOCRVL(**kwargs)


def _geometry_from_bbox(bbox, width, height) -> dict | None:
    if not bbox or not isinstance(bbox, (list, tuple)) or len(bbox) < 4:
        return None
    try:
        if isinstance(bbox[0], (list, tuple)):
            xs = [float(point[0]) for point in bbox]
            ys = [float(point[1]) for point in bbox]
            coords = [min(xs), min(ys), max(xs), max(ys)]
        else:
            coords = [float(bbox[0]), float(bbox[1]), float(bbox[2]), float(bbox[3])]
    except (TypeError, ValueError, IndexError):
        return None

    return {
        "bbox": coords,
        "coordinate_system": "image_pixels_topleft",
        "page_width": float(width or 0.0),
        "page_height": float(height or 0.0),
    }


def build_page_ir_from_paddle(res_item, page_num: int, doc_id: str) -> dict:
    """Build typed-IR-compatible page data from public PaddleOCR-VL result JSON."""
    page_id = f"{doc_id}_p{page_num:04d}"
    blocks = []
    tables = []
    page_texts = []

    res_dict = {}
    if hasattr(res_item, "json"):
        json_attr = res_item.json
        if callable(json_attr):
            res_dict = json_attr()
        elif isinstance(json_attr, dict):
            res_dict = json_attr
    elif isinstance(res_item, dict):
        res_dict = res_item

    inner_res = res_dict.get("res", res_dict) if isinstance(res_dict, dict) else {}
    width = inner_res.get("width") if isinstance(inner_res, dict) else None
    height = inner_res.get("height") if isinstance(inner_res, dict) else None
    width = float(width) if width is not None else None
    height = float(height) if height is not None else None

    parsing_list = (
        inner_res.get("parsing_res_list", inner_res.get("layout", []))
        if isinstance(inner_res, dict)
        else []
    )
    if not isinstance(parsing_list, list) and isinstance(res_item, list):
        parsing_list = res_item

    table_idx = 0
    if isinstance(parsing_list, list):
        for idx, item in enumerate(parsing_list):
            if not isinstance(item, dict):
                continue

            content_str = str(
                item.get("block_content", item.get("text", item.get("transcription", "")))
            ).strip()
            label_str = str(
                item.get("block_label", item.get("type", item.get("label", "text")))
            ).lower()
            order_val = item.get("block_order", item.get("reading_order", idx))
            block_id = str(item.get("block_id", f"{page_id}_b{idx:05d}"))
            block_bbox = item.get("block_bbox", item.get("bbox", item.get("poly")))
            block_geometry = _geometry_from_bbox(block_bbox, width, height)

            if label_str == "table" and ("table_cells" in item or "table_html" in item):
                cells_raw = item.get("table_cells", [])
                if isinstance(cells_raw, list) and cells_raw:
                    cells_data = []
                    max_r, max_c = 0, 0
                    table_id = f"{page_id}_t{table_idx:03d}"
                    for cell_raw in cells_raw:
                        if not isinstance(cell_raw, dict):
                            continue
                        row_index = int(cell_raw.get("row_index", 0))
                        col_index = int(cell_raw.get("col_index", 0))
                        max_r = max(max_r, row_index + 1)
                        max_c = max(max_c, col_index + 1)
                        cell_bbox = cell_raw.get(
                            "cell_bbox", cell_raw.get("bbox", cell_raw.get("poly"))
                        )
                        cells_data.append(
                            {
                                "cell_id": f"{table_id}_r{row_index:03d}_c{col_index:03d}",
                                "row_index": row_index,
                                "col_index": col_index,
                                "text": str(cell_raw.get("text", "")).strip(),
                                "geometry": _geometry_from_bbox(cell_bbox, width, height),
                            }
                        )
                    tables.append(
                        {
                            "table_id": table_id,
                            "page_number": page_num,
                            "row_count": max_r,
                            "col_count": max_c,
                            "cells": cells_data,
                            "geometry": block_geometry,
                        }
                    )
                    table_idx += 1

            if content_str:
                page_texts.append(content_str)
                blocks.append(
                    {
                        "block_id": block_id,
                        "page_number": page_num,
                        "block_type": label_str,
                        "text": content_str,
                        "reading_order": int(order_val),
                        "geometry": block_geometry,
                    }
                )

    return {
        "page_id": page_id,
        "page_number": page_num,
        "width": width,
        "height": height,
        "blocks": blocks,
        "tables": tables,
        "text_content": "\n".join(page_texts),
    }


def _safe_error(req_id: str, parser_id: str, versions: dict, code: str, message: str) -> dict:
    return {
        "request_id": req_id,
        "success": False,
        "actual_parser_id": parser_id,
        "actual_parser_version": versions.get("paddleocr", "unknown"),
        "runtime_versions": versions,
        "error_type": code,
        "error_message": message,
    }


def main():
    start_time = time.time()
    req_data = {}
    try:
        raw_input = sys.stdin.read()
        if not raw_input.strip():
            sys.stderr.write("No input JSON received on stdin\n")
            sys.exit(1)

        req_data = json.loads(raw_input)
        req_id = req_data.get("request_id", "req_unknown")
        parser_id = req_data.get("parser_id", "paddleocr_vl")
        operation = req_data.get("operation", "parse")
        input_path = req_data.get("input_path", "")
        doc_id = req_data.get("document_id", "doc_unknown")
        source_sha256 = req_data.get("source_sha256", "")
        options = req_data.get("options", {}) or {}
        allow_model_download = bool(req_data.get("allow_model_download", False)) or (
            os.getenv("ALLOW_MODEL_DOWNLOAD") == "1"
        )

        versions = get_runtime_versions()
        has_paddle = importlib.util.find_spec("paddle") is not None
        has_paddleocr = importlib.util.find_spec("paddleocr") is not None
        symbol_importable = False
        if has_paddle and has_paddleocr:
            try:
                from paddleocr import PaddleOCRVL  # noqa: F401

                symbol_importable = True
            except Exception:
                symbol_importable = False

        backend = str(options.get("vl_rec_backend", _LOCAL_VL_BACKEND))
        local_backend = backend == _LOCAL_VL_BACKEND
        cache_status, explicit_ready = check_model_cache_status(options)
        model_cache_ready = explicit_ready or allow_model_download
        runtime_ready = has_paddle and has_paddleocr and symbol_importable
        offline_runtime_ready = runtime_ready and explicit_ready and local_backend and not allow_model_download

        if operation == "healthcheck":
            response = {
                "request_id": req_id,
                "success": runtime_ready and model_cache_ready and local_backend,
                "actual_parser_id": parser_id,
                "actual_parser_version": versions.get("paddleocr", "unknown"),
                "runtime_versions": versions,
                "health_data": {
                    "python_executable": sys.executable,
                    "paddle_installed": has_paddle,
                    "paddle_version": versions.get("paddle"),
                    "paddleocr_installed": has_paddleocr,
                    "paddleocr_version": versions.get("paddleocr"),
                    "symbol_importable": symbol_importable,
                    "pipeline_version": options.get("pipeline_version", "v1.6"),
                    "vl_rec_backend": backend,
                    "local_backend": local_backend,
                    "model_cache_status": cache_status,
                    "model_loaded": False,
                    "runtime_ready": runtime_ready,
                    "model_cache_ready": model_cache_ready,
                    "offline_runtime_ready": offline_runtime_ready,
                    "download_allowed": allow_model_download,
                    "layout_model_dir_configured": bool(options.get("layout_detection_model_dir")),
                    "vl_rec_model_dir_configured": bool(options.get("vl_rec_model_dir")),
                },
            }
            print(json.dumps(response), flush=True)
            return

        if operation != "parse":
            print(
                json.dumps(
                    _safe_error(
                        req_id,
                        parser_id,
                        versions,
                        "UNSUPPORTED_WORKER_OPERATION",
                        f"Unsupported PaddleOCR-VL worker operation: {operation}",
                    )
                ),
                flush=True,
            )
            return

        if not runtime_ready:
            print(
                json.dumps(
                    _safe_error(
                        req_id,
                        parser_id,
                        versions,
                        "PARSER_UNAVAILABLE",
                        "Paddle / PaddleOCR unavailable or PaddleOCRVL is not importable.",
                    )
                ),
                flush=True,
            )
            return

        if not local_backend:
            print(
                json.dumps(
                    _safe_error(
                        req_id,
                        parser_id,
                        versions,
                        "REMOTE_BACKEND_REJECTED",
                        "Phase 9E permits only the local/native PaddleOCR-VL backend.",
                    )
                ),
                flush=True,
            )
            return

        if not model_cache_ready:
            print(
                json.dumps(
                    _safe_error(
                        req_id,
                        parser_id,
                        versions,
                        "PADDLEOCR_VL_CACHE_NOT_READY",
                        f"Explicit PaddleOCR-VL model directories are not ready ({cache_status}).",
                    )
                ),
                flush=True,
            )
            return

        input_file = Path(input_path)
        if not input_file.is_file() or input_file.suffix.lower() != ".pdf":
            print(
                json.dumps(
                    _safe_error(
                        req_id,
                        parser_id,
                        versions,
                        "INVALID_PADDLEOCR_VL_INPUT",
                        "PaddleOCR-VL canary input must be an existing PDF.",
                    )
                ),
                flush=True,
            )
            return

        pipeline = create_paddleocr_vl_pipeline(options)
        predict_iter = getattr(pipeline, "predict_iter", None)
        if callable(predict_iter):
            raw_output = predict_iter(input=str(input_file))
        else:
            raw_output = pipeline.predict(input=str(input_file))
        results = list(raw_output) if raw_output is not None else []

        if not results:
            print(
                json.dumps(
                    _safe_error(
                        req_id,
                        parser_id,
                        versions,
                        "PARSER_EMPTY_OUTPUT",
                        "PaddleOCR-VL returned no page results.",
                    )
                ),
                flush=True,
            )
            return

        pages = [
            build_page_ir_from_paddle(result_item, page_index + 1, doc_id)
            for page_index, result_item in enumerate(results)
        ]
        elapsed = time.time() - start_time
        doc_ir_dict = {
            "document_id": doc_id,
            "source_document": {
                "document_id": doc_id,
                "filename": input_file.name,
                "path": str(input_file),
                "sha256": source_sha256,
                "page_count": len(pages),
            },
            "provenance": {
                "parser_id": parser_id,
                "parser_version": versions.get("paddleocr", "unknown"),
                "execution_time_seconds": elapsed,
                "config": {
                    key: value
                    for key, value in options.items()
                    if key not in {"layout_detection_model_dir", "vl_rec_model_dir"}
                },
            },
            "pages": pages,
            "full_text": "\n\n".join(page["text_content"] for page in pages),
            "warnings": [
                {
                    "code": "PADDLEOCR_VL_VISUAL_CANARY_EXECUTED",
                    "message": "PaddleOCR-VL local visual/layout parser executed.",
                }
            ],
        }
        response = {
            "request_id": req_id,
            "success": True,
            "actual_parser_id": parser_id,
            "actual_parser_version": versions.get("paddleocr", "unknown"),
            "runtime_versions": versions,
            "document_ir_dict": doc_ir_dict,
            "warnings": [],
        }
        print(json.dumps(response), flush=True)

    except Exception as exc:
        logger.exception("PaddleOCR-VL worker error")
        versions = get_runtime_versions()
        req_id = req_data.get("request_id", "req_unknown")
        parser_id = req_data.get("parser_id", "paddleocr_vl")
        print(
            json.dumps(
                _safe_error(
                    req_id,
                    parser_id,
                    versions,
                    f"PADDLEOCR_VL_{type(exc).__name__.upper()}",
                    f"PaddleOCR-VL worker failed: {type(exc).__name__}",
                )
            ),
            flush=True,
        )


if __name__ == "__main__":
    main()
