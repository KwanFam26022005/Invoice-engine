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


def build_page_ir_from_paddle(res_item, page_num: int, doc_id: str) -> dict:
    """Build per-page IR dictionary from PaddleOCR-VL res_item public result JSON."""
    page_id = f"{doc_id}_p{page_num:04d}"
    blocks = []
    tables = []
    page_texts = []

    # Extract JSON dict from public result interface
    res_dict = {}
    if hasattr(res_item, "json"):
        json_attr = res_item.json
        if callable(json_attr):
            res_dict = json_attr()
        elif isinstance(json_attr, dict):
            res_dict = json_attr
    elif isinstance(res_item, dict):
        res_dict = res_item

    # Standard public result JSON structure: {"res": {"width": ..., "height": ..., "parsing_res_list": [...]}}
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
                if isinstance(bbox[0], (list, tuple)):  # polygon [[x0, y0], ...]
                    xs = [p[0] for p in bbox]
                    ys = [p[1] for p in bbox]
                    bbox_dict = {
                        "x0": float(min(xs)),
                        "y0": float(min(ys)),
                        "x1": float(max(xs)),
                        "y1": float(max(ys)),
                        "page_number": page_num,
                    }
                else:  # [x0, y0, x1, y1]
                    bbox_dict = {
                        "x0": float(bbox[0]),
                        "y0": float(bbox[1]),
                        "x1": float(bbox[2]),
                        "y1": float(bbox[3]),
                        "page_number": page_num,
                    }

            # Handle structured table if cell layout is provided
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
        input_path = req_data.get("input_path", "")
        doc_id = req_data.get("document_id", "doc_unknown")
        options = req_data.get("options", {})
        allow_model_download = req_data.get("allow_model_download", False)

        runtime_versions = get_runtime_versions()

        # Check dependencies
        has_paddle = importlib.util.find_spec("paddle") is not None
        has_paddleocr = importlib.util.find_spec("paddleocr") is not None

        if not (has_paddle and has_paddleocr):
            resp = {
                "request_id": req_id,
                "success": False,
                "actual_parser_id": parser_id,
                "actual_parser_version": "3.0.0",
                "runtime_versions": runtime_versions,
                "error_type": "PARSER_UNAVAILABLE",
                "error_message": "Paddle / PaddleOCR dependency not installed in worker environment.",
            }
            print(json.dumps(resp), flush=True)
            return

        # Offline policy check for specific model artifacts
        if not allow_model_download and os.getenv("ALLOW_MODEL_DOWNLOAD") != "1":
            user_home = Path.home()
            paddle_model_dir = user_home / ".paddleocr"
            # Verify specific model artifacts exist
            if not paddle_model_dir.exists() or not any(paddle_model_dir.rglob("*.pdiparams")):
                resp = {
                    "request_id": req_id,
                    "success": False,
                    "actual_parser_id": parser_id,
                    "actual_parser_version": "3.0.0",
                    "runtime_versions": runtime_versions,
                    "error_type": "PARSER_UNAVAILABLE",
                    "error_message": "PaddleOCR required model artifacts (.pdiparams) not found in cache and ALLOW_MODEL_DOWNLOAD is not set.",
                }
                print(json.dumps(resp), flush=True)
                return

        # Attempt importing official PaddleOCRVL
        from paddleocr import PaddleOCRVL

        pipeline = PaddleOCRVL(
            pipeline_version=options.get("pipeline_version", "v1.6"),
            device=options.get("device", "cpu"),
            engine=options.get("engine", "paddle"),
            use_doc_orientation_classify=options.get(
                "use_doc_orientation_classify", False
            ),
            use_doc_unwarping=options.get("use_doc_unwarping", False),
            use_layout_detection=options.get("use_layout_detection", True),
            use_chart_recognition=options.get("use_chart_recognition", False),
            use_seal_recognition=options.get("use_seal_recognition", False),
            use_ocr_for_image_block=options.get("use_ocr_for_image_block", False),
        )

        results = pipeline.predict(input=str(input_path))

        pages = []
        if isinstance(results, list):
            for p_idx, res_item in enumerate(results):
                page_ir_dict = build_page_ir_from_paddle(
                    res_item, p_idx + 1, doc_id
                )
                pages.append(page_ir_dict)

        elapsed = time.time() - start_time
        doc_ir_dict = {
            "document_id": doc_id,
            "source_document": {
                "document_id": doc_id,
                "path": input_path,
                "file_name": Path(input_path).name,
                "page_count": len(pages) or 1,
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
