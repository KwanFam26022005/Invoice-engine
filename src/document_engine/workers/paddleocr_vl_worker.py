"""Standalone worker process for running PaddleOCR-VL fallback parser using official API."""

import importlib.util
import json
import logging
import os
from pathlib import Path
import sys
import time

logging.basicConfig(level=logging.INFO, stream=sys.stderr)
logger = logging.getLogger("paddleocr_vl_worker")


def get_runtime_versions() -> dict:
    versions = {
        "python": sys.version.split()[0],
    }
    for pkg in ("paddle", "paddleocr", "pydantic"):
        try:
            mod = importlib.import_module(pkg)
            versions[pkg] = getattr(mod, "__version__", "installed")
        except Exception:
            pass
    return versions


def check_model_cache_status(options: dict) -> tuple[str, bool]:
    """Inspect local PaddleOCR model cache readiness."""
    layout_dir = options.get("layout_detection_model_dir")
    vl_rec_dir = options.get("vl_rec_model_dir")

    # 1. Explicit Local Model Dirs
    if layout_dir or vl_rec_dir:
        if not layout_dir or not vl_rec_dir:
            return "LOCAL_MODEL_DIRS_INVALID", False

        p_layout = Path(layout_dir)
        p_vl = Path(vl_rec_dir)

        if not (p_layout.is_dir() and p_vl.is_dir()):
            return "LOCAL_MODEL_DIRS_INVALID", False

        # Validate non-empty
        try:
            layout_has_files = any(p_layout.iterdir())
            vl_has_files = any(p_vl.iterdir())
        except Exception:
            return "LOCAL_MODEL_DIRS_INVALID", False

        if not (layout_has_files and vl_has_files):
            return "LOCAL_MODEL_DIRS_INVALID", False

        return "READY_LOCAL_MODEL_DIRS", True

    # 2. Inspect runtime default cache locations (~/.paddleocr and ~/.paddlex/official_models)
    user_home = Path.home()
    paddle_cache = user_home / ".paddleocr"
    paddlex_cache = user_home / ".paddlex" / "official_models"

    has_paddle_files = paddle_cache.exists() and any(paddle_cache.rglob("*.pdiparams"))
    has_paddlex_files = paddlex_cache.exists() and any(paddlex_cache.rglob("*"))

    if has_paddle_files or has_paddlex_files:
        # Default cache scan is partially verified and NOT model_cache_ready
        return "MODEL_CACHE_PARTIALLY_VERIFIED", False

    return "CACHE_MISSING", False


def create_paddleocr_vl_pipeline(options: dict):
    """Factory function for instantiating PaddleOCRVL pipeline."""
    from paddleocr import PaddleOCRVL

    kwargs = {
        "pipeline_version": options.get("pipeline_version", "v1.6"),
        "device": options.get("device", "cpu"),
        "engine": options.get("engine", "paddle"),
        "use_doc_orientation_classify": options.get(
            "use_doc_orientation_classify", False
        ),
        "use_doc_unwarping": options.get("use_doc_unwarping", False),
        "use_layout_detection": options.get("use_layout_detection", True),
        "use_chart_recognition": options.get("use_chart_recognition", False),
        "use_seal_recognition": options.get("use_seal_recognition", False),
        "use_ocr_for_image_block": options.get("use_ocr_for_image_block", False),
    }

    if "layout_detection_model_dir" in options:
        kwargs["layout_detection_model_dir"] = options["layout_detection_model_dir"]
    if "vl_rec_model_dir" in options:
        kwargs["vl_rec_model_dir"] = options["vl_rec_model_dir"]

    return PaddleOCRVL(**kwargs)


def build_page_ir_from_paddle(res_item, page_num: int, doc_id: str) -> dict:
    """Build per-page IR dictionary from PaddleOCR-VL res_item public result JSON."""
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
    if width is not None:
        width = float(width)
    if height is not None:
        height = float(height)

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
            b_id = item.get("block_id", f"{page_id}_b{idx:05d}")

            bbox = item.get("block_bbox", item.get("bbox", item.get("poly")))
            bbox_dict = None
            if bbox and isinstance(bbox, (list, tuple)) and len(bbox) >= 4:
                if isinstance(bbox[0], (list, tuple)):
                    xs = [p[0] for p in bbox]
                    ys = [p[1] for p in bbox]
                    bbox_dict = {
                        "x0": float(min(xs)),
                        "y0": float(min(ys)),
                        "x1": float(max(xs)),
                        "y1": float(max(ys)),
                        "page_number": page_num,
                    }
                else:
                    bbox_dict = {
                        "x0": float(bbox[0]),
                        "y0": float(bbox[1]),
                        "x1": float(bbox[2]),
                        "y1": float(bbox[3]),
                        "page_number": page_num,
                    }

            if label_str == "table" and ("table_cells" in item or "table_html" in item):
                cells_raw = item.get("table_cells", [])
                if cells_raw:
                    cells_data = []
                    max_r, max_c = 0, 0
                    for c_raw in cells_raw:
                        r_i = c_raw.get("row_index", 0)
                        c_i = c_raw.get("col_index", 0)
                        max_r = max(max_r, r_i + 1)
                        max_c = max(max_c, c_i + 1)
                        cells_data.append(
                            {
                                "cell_id": f"{page_id}_t{table_idx}_r{r_i}_c{c_i}",
                                "row_index": r_i,
                                "col_index": c_i,
                                "text": str(c_raw.get("text", "")).strip(),
                                "bbox": None,
                            }
                        )
                    tables.append(
                        {
                            "table_id": f"{page_id}_t{table_idx:03d}",
                            "page_number": page_num,
                            "row_count": max_r,
                            "col_count": max_c,
                            "cells": cells_data,
                            "bbox": bbox_dict,
                        }
                    )
                    table_idx += 1

            if content_str:
                page_texts.append(content_str)
                blocks.append(
                    {
                        "block_id": str(b_id),
                        "page_number": page_num,
                        "text": content_str,
                        "label": label_str,
                        "reading_order": int(order_val),
                        "bbox": bbox_dict,
                    }
                )

    page_text_content = "\n".join(page_texts)

    return {
        "page_id": page_id,
        "page_number": page_num,
        "width": width,
        "height": height,
        "blocks": blocks,
        "tables": tables,
        "text_content": page_text_content,
    }


def main():
    start_time = time.time()
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
        options = req_data.get("options", {})
        allow_model_download = req_data.get("allow_model_download", False) or os.getenv("ALLOW_MODEL_DOWNLOAD") == "1"

        runtime_versions = get_runtime_versions()

        # Check dependencies
        has_paddle = importlib.util.find_spec("paddle") is not None
        has_paddleocr = importlib.util.find_spec("paddleocr") is not None
        symbol_importable = False
        if has_paddle and has_paddleocr:
            try:
                from paddleocr import PaddleOCRVL  # noqa: F401
                symbol_importable = True
            except Exception:
                symbol_importable = False

        cache_status, explicit_ready = check_model_cache_status(options)
        model_cache_ready = explicit_ready or allow_model_download
        runtime_ready = has_paddle and has_paddleocr and symbol_importable

        # Handle healthcheck operation
        if operation == "healthcheck":
            resp = {
                "request_id": req_id,
                "success": runtime_ready and model_cache_ready,
                "actual_parser_id": parser_id,
                "actual_parser_version": runtime_versions.get("paddleocr", "3.0.0"),
                "runtime_versions": runtime_versions,
                "health_data": {
                    "python_executable": sys.executable,
                    "paddle_installed": has_paddle,
                    "paddle_version": runtime_versions.get("paddle"),
                    "paddleocr_installed": has_paddleocr,
                    "paddleocr_version": runtime_versions.get("paddleocr"),
                    "symbol_importable": symbol_importable,
                    "model_cache_status": cache_status,
                    "model_loaded": False,
                    "runtime_ready": runtime_ready,
                    "model_cache_ready": model_cache_ready,
                },
            }
            print(json.dumps(resp), flush=True)
            return

        if not runtime_ready:
            resp = {
                "request_id": req_id,
                "success": False,
                "actual_parser_id": parser_id,
                "actual_parser_version": "3.0.0",
                "runtime_versions": runtime_versions,
                "error_type": "PARSER_UNAVAILABLE",
                "error_message": "Paddle / PaddleOCR dependency not installed or PaddleOCRVL symbol not importable in worker environment.",
            }
            print(json.dumps(resp), flush=True)
            return

        # Do NOT instantiate model if allow_model_download is False and cache is not ready
        if not model_cache_ready:
            resp = {
                "request_id": req_id,
                "success": False,
                "actual_parser_id": parser_id,
                "actual_parser_version": "3.0.0",
                "runtime_versions": runtime_versions,
                "error_type": "PARSER_UNAVAILABLE",
                "error_message": f"PaddleOCR-VL model cache unready (status: {cache_status}) and ALLOW_MODEL_DOWNLOAD is not set.",
            }
            print(json.dumps(resp), flush=True)
            return

        # Instantiate pipeline using factory function
        pipeline = create_paddleocr_vl_pipeline(options)

        raw_output = pipeline.predict(input=str(input_path))
        results = list(raw_output) if raw_output is not None else []

        if not results:
            resp = {
                "request_id": req_id,
                "success": False,
                "actual_parser_id": parser_id,
                "actual_parser_version": runtime_versions.get("paddleocr", "3.0.0"),
                "runtime_versions": runtime_versions,
                "error_type": "PARSER_EMPTY_OUTPUT",
                "error_message": "PaddleOCR-VL predict returned empty output.",
            }
            print(json.dumps(resp), flush=True)
            return

        pages = []
        for p_idx, res_item in enumerate(results):
            page_ir_dict = build_page_ir_from_paddle(res_item, p_idx + 1, doc_id)
            pages.append(page_ir_dict)

        elapsed = time.time() - start_time
        doc_ir_dict = {
            "document_id": doc_id,
            "source_document": {
                "document_id": doc_id,
                "path": input_path,
                "file_name": Path(input_path).name,
                "page_count": len(pages),
            },
            "provenance": {
                "parser_id": parser_id,
                "parser_version": runtime_versions.get("paddleocr", "3.0.0"),
                "execution_time_seconds": elapsed,
                "config": options,
            },
            "pages": pages,
            "full_text": "\n\n".join(p["text_content"] for p in pages),
            "warnings": [
                {
                    "code": "PADDLEOCR_VL_FALLBACK_EXECUTED",
                    "message": "PaddleOCR-VL official pipeline executed.",
                }
            ],
        }

        resp = {
            "request_id": req_id,
            "success": True,
            "actual_parser_id": parser_id,
            "actual_parser_version": runtime_versions.get("paddleocr", "3.0.0"),
            "runtime_versions": runtime_versions,
            "document_ir_dict": doc_ir_dict,
            "warnings": [],
        }
        print(json.dumps(resp), flush=True)

    except Exception as e:
        logger.exception("PaddleOCR-VL worker error")
        resp = {
            "request_id": req_data.get("request_id", "req_unknown")
            if "req_data" in locals()
            else "req_unknown",
            "success": False,
            "actual_parser_id": req_data.get("parser_id", "paddleocr_vl")
            if "req_data" in locals()
            else "paddleocr_vl",
            "actual_parser_version": "3.0.0",
            "runtime_versions": get_runtime_versions(),
            "error_type": "WORKER_PARSE_FAILED",
            "error_message": f"PaddleOCR-VL parsing failed: {e!s}",
        }
        print(json.dumps(resp), flush=True)


if __name__ == "__main__":
    main()
