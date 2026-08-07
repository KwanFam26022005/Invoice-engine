"""Standalone worker process for running PaddleOCR-VL fallback parser."""

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
    """Build per-page IR dictionary from PaddleOCR-VL prediction result item."""
    page_id = f"{doc_id}_p{page_num}"
    blocks = []
    tables = []
    page_texts = []
    block_idx = 0
    table_idx = 0

    width = 595.0
    height = 842.0

    # Inspect Paddle res_item format (dict or object)
    if isinstance(res_item, dict):
        layout_res = res_item.get("layout", res_item.get("res", []))
    elif hasattr(res_item, "get"):
        layout_res = res_item.get("layout", [])
    elif isinstance(res_item, list):
        layout_res = res_item
    else:
        layout_res = getattr(res_item, "layout", [])

    if isinstance(layout_res, list):
        for item in layout_res:
            text_str = ""
            label_str = "text"
            bbox_dict = None

            if isinstance(item, dict):
                text_str = str(item.get("text", item.get("transcription", ""))).strip()
                label_str = str(item.get("type", item.get("label", "text"))).lower()
                bbox = item.get("bbox", item.get("poly"))
                if bbox and isinstance(bbox, (list, tuple)) and len(bbox) >= 4:
                    if isinstance(bbox[0], (list, tuple)):  # polygon
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

                # Check for table structure
                if label_str == "table" or "table" in item:
                    table_html = item.get("html", "")
                    cells_data = []

                    tables.append(
                        {
                            "table_id": f"{page_id}_t{table_idx}",
                            "page_number": page_num,
                            "row_count": 0,
                            "column_count": 0,
                            "cells": cells_data,
                            "bbox": bbox_dict,
                        }
                    )
                    table_idx += 1

            if text_str:
                page_texts.append(text_str)
                blocks.append(
                    {
                        "block_id": f"{page_id}_b{block_idx}",
                        "page_number": page_num,
                        "text": text_str,
                        "label": label_str,
                        "reading_order": block_idx,
                        "bbox": bbox_dict,
                    }
                )
                block_idx += 1

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

        # Offline policy check
        if not allow_model_download and os.getenv("ALLOW_MODEL_DOWNLOAD") != "1":
            user_home = Path.home()
            paddle_model_dir = user_home / ".paddleocr"
            if not paddle_model_dir.exists():
                resp = {
                    "request_id": req_id,
                    "success": False,
                    "actual_parser_id": parser_id,
                    "actual_parser_version": "3.0.0",
                    "runtime_versions": runtime_versions,
                    "error_type": "PARSER_UNAVAILABLE",
                    "error_message": "PaddleOCR model cache not found and ALLOW_MODEL_DOWNLOAD is not set.",
                }
                print(json.dumps(resp), flush=True)
                return

        # Attempt importing official PaddleOCRVL
        from paddleocr import PaddleOCRVL

        pipeline = PaddleOCRVL(
            pipeline_version=options.get("pipeline_version", "v1.6"),
            use_gpu=options.get("use_gpu", False),
            use_angle_cls=options.get("use_angle_cls", False),
            use_doc_unwarp=options.get("use_doc_unwarp", False),
            use_doc_orientation_classify=options.get(
                "use_doc_orientation_classify", False
            ),
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
        logger.error("PaddleOCR-VL worker error: %s", e, exc_info=True)
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
            "error_message": f"PaddleOCR-VL parsing failed: {str(e)}",
        }
        print(json.dumps(resp), flush=True)


if __name__ == "__main__":
    main()
