"""Standalone worker process for running Docling Native and Docling OCR parsers."""

import importlib.util
import json
import logging
import os
from pathlib import Path
import sys
import time

logging.basicConfig(level=logging.INFO, stream=sys.stderr)
logger = logging.getLogger("docling_worker")


def get_runtime_versions() -> dict:
    versions = {
        "python": sys.version.split()[0],
    }
    for pkg in ("docling", "docling_core", "easyocr", "pydantic", "torch"):
        try:
            mod = importlib.import_module(pkg)
            versions[pkg] = getattr(mod, "__version__", "installed")
        except Exception:
            pass
    return versions


def build_page_ir_from_docling(
    docling_doc, page_num: int, doc_id: str
) -> dict:
    """Build per-page IR dictionary from a Docling document object."""
    page_id = f"{doc_id}_p{page_num}"
    blocks = []
    tables = []

    # Determine page size if available
    width = None
    height = None
    if hasattr(docling_doc, "pages") and isinstance(docling_doc.pages, dict):
        page_obj = docling_doc.pages.get(page_num)
        if page_obj and hasattr(page_obj, "size") and page_obj.size:
            w_val = getattr(page_obj.size, "width", None)
            h_val = getattr(page_obj.size, "height", None)
            width = float(w_val) if w_val is not None else None
            height = float(h_val) if h_val is not None else None

    page_texts = []
    block_idx = 0

    # Iterate document items
    if hasattr(docling_doc, "iterate_items"):
        for item, level in docling_doc.iterate_items():
            # Filter item by page number provenance if available
            item_page_num = page_num
            bbox_dict = None
            if hasattr(item, "prov") and item.prov:
                prov_0 = item.prov[0]
                item_page_num = getattr(prov_0, "page_no", page_num)
                if item_page_num != page_num:
                    continue
                if hasattr(prov_0, "bbox") and prov_0.bbox:
                    b = prov_0.bbox
                    bbox_dict = {
                        "x0": float(getattr(b, "l", getattr(b, "x0", 0.0))),
                        "y0": float(getattr(b, "t", getattr(b, "y0", 0.0))),
                        "x1": float(getattr(b, "r", getattr(b, "x1", 0.0))),
                        "y1": float(getattr(b, "b", getattr(b, "y1", 0.0))),
                        "page_number": page_num,
                    }

            text_str = str(getattr(item, "text", "")).strip()
            label_str = str(getattr(item, "label", "text")).lower()

            # Handle tables separately if item is table
            if label_str == "table" or hasattr(item, "data"):
                # Handle table item below
                pass

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

    # Extract tables
    table_idx = 0
    if hasattr(docling_doc, "tables") and docling_doc.tables:
        for tbl in docling_doc.tables:
            tbl_page_num = page_num
            if hasattr(tbl, "prov") and tbl.prov:
                tbl_page_num = getattr(tbl.prov[0], "page_no", page_num)
            if tbl_page_num != page_num:
                continue

            cells_data = []
            rows_cnt = 0
            cols_cnt = 0

            # Try table data structure
            if hasattr(tbl, "data") and hasattr(tbl.data, "table_cells"):
                for cell in tbl.data.table_cells:
                    r_idx = getattr(cell, "start_row_offset_idx", 0)
                    c_idx = getattr(cell, "start_col_offset_idx", 0)
                    cell_text = str(getattr(cell, "text", "")).strip()
                    rows_cnt = max(rows_cnt, r_idx + 1)
                    cols_cnt = max(cols_cnt, c_idx + 1)
                    cells_data.append(
                        {
                            "cell_id": f"{page_id}_t{table_idx}_r{r_idx}_c{c_idx}",
                            "row_index": r_idx,
                            "column_index": c_idx,
                            "text": cell_text,
                            "bbox": None,
                        }
                    )

            tables.append(
                {
                    "table_id": f"{page_id}_t{table_idx}",
                    "page_number": page_num,
                    "row_count": rows_cnt,
                    "column_count": cols_cnt,
                    "cells": cells_data,
                    "bbox": None,
                }
            )
            table_idx += 1

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
        parser_id = req_data.get("parser_id", "docling_native")
        input_path = req_data.get("input_path", "")
        doc_id = req_data.get("document_id", "doc_unknown")
        options = req_data.get("options", {})
        allow_model_download = req_data.get("allow_model_download", False)

        runtime_versions = get_runtime_versions()

        operation = req_data.get("operation", "parse")
        has_docling = importlib.util.find_spec("docling") is not None

        if operation == "healthcheck":
            has_easyocr = importlib.util.find_spec("easyocr") is not None
            user_home = Path.home()
            easyocr_model_dir = user_home / ".EasyOCR"
            easyocr_cached = easyocr_model_dir.exists() and any(easyocr_model_dir.rglob("*.pth"))
            runtime_ready = has_docling and (parser_id != "docling_ocr" or has_easyocr)
            model_cache_ready = (
                parser_id != "docling_ocr"
                or easyocr_cached
                or allow_model_download
                or os.getenv("ALLOW_MODEL_DOWNLOAD") == "1"
            )
            resp = {
                "request_id": req_id,
                "success": runtime_ready and model_cache_ready,
                "actual_parser_id": parser_id,
                "actual_parser_version": runtime_versions.get("docling", "2.0.0"),
                "runtime_versions": runtime_versions,
                "health_data": {
                    "python_executable": sys.executable,
                    "docling_installed": has_docling,
                    "docling_version": runtime_versions.get("docling"),
                    "easyocr_installed": has_easyocr,
                    "easyocr_version": runtime_versions.get("easyocr"),
                    "model_cache_ready": model_cache_ready,
                    "runtime_ready": runtime_ready,
                },
            }
            print(json.dumps(resp), flush=True)
            return

        if not has_docling:
            resp = {
                "request_id": req_id,
                "success": False,
                "actual_parser_id": parser_id,
                "actual_parser_version": "2.0.0",
                "runtime_versions": runtime_versions,
                "error_type": "PARSER_UNAVAILABLE",
                "error_message": "Docling package is not installed in worker environment.",
            }
            print(json.dumps(resp), flush=True)
            return

        if parser_id == "docling_ocr" and importlib.util.find_spec("easyocr") is None:
            resp = {
                "request_id": req_id,
                "success": False,
                "actual_parser_id": parser_id,
                "actual_parser_version": "2.0.0",
                "runtime_versions": runtime_versions,
                "error_type": "PARSER_UNAVAILABLE",
                "error_message": "EasyOCR package is not installed for Docling OCR.",
            }
            print(json.dumps(resp), flush=True)
            return

        # Check offline policy flag
        if (
            not allow_model_download
            and os.getenv("ALLOW_MODEL_DOWNLOAD") != "1"
            and parser_id == "docling_ocr"
        ):
            # Check if easyocr model cache exists or allow flag
            user_home = Path.home()
            easyocr_model_dir = user_home / ".EasyOCR"
            if not easyocr_model_dir.exists():
                resp = {
                    "request_id": req_id,
                    "success": False,
                    "actual_parser_id": parser_id,
                    "actual_parser_version": "2.0.0",
                    "runtime_versions": runtime_versions,
                    "error_type": "PARSER_UNAVAILABLE",
                    "error_message": "EasyOCR models not cached and ALLOW_MODEL_DOWNLOAD is not set.",
                }
                print(json.dumps(resp), flush=True)
                return

        # Import docling converter modules
        from docling.document_converter import DocumentConverter, PdfFormatOption
        from docling.datamodel.pipeline_options import PdfPipelineOptions

        pipeline_options = PdfPipelineOptions()
        do_ocr = bool(options.get("do_ocr", parser_id == "docling_ocr"))
        pipeline_options.do_ocr = do_ocr
        pipeline_options.do_table_structure = bool(
            options.get("do_table_structure", True)
        )

        if do_ocr:
            try:
                from docling.datamodel.pipeline_options import EasyOcrOptions

                pipeline_options.ocr_options = EasyOcrOptions(
                    lang=options.get("ocr_languages", ["vi", "en"])
                )
            except Exception as ocr_err:
                logger.warning("Could not set EasyOcrOptions: %s", ocr_err)

        converter = DocumentConverter(
            format_options={
                "pdf": PdfFormatOption(pipeline_options=pipeline_options)
            }
        )

        result = converter.convert(input_path)
        docling_doc = result.document
        full_markdown = (
            docling_doc.export_to_markdown()
            if hasattr(docling_doc, "export_to_markdown")
            else ""
        )

        # Estimate or obtain total page count
        page_count = req_data.get("page_count", 1)
        if hasattr(docling_doc, "pages") and isinstance(docling_doc.pages, dict) and docling_doc.pages:
            page_count = len(docling_doc.pages)

        pages = []
        for p in range(1, page_count + 1):
            page_ir_dict = build_page_ir_from_docling(docling_doc, p, doc_id)
            pages.append(page_ir_dict)

        elapsed = time.time() - start_time
        doc_ir_dict = {
            "document_id": doc_id,
            "source_document": {
                "document_id": doc_id,
                "path": input_path,
                "file_name": Path(input_path).name,
                "page_count": page_count,
            },
            "provenance": {
                "parser_id": parser_id,
                "parser_version": runtime_versions.get("docling", "2.0.0"),
                "execution_time_seconds": elapsed,
                "config": options,
            },
            "pages": pages,
            "full_text": full_markdown or "\n\n".join(p["text_content"] for p in pages),
            "warnings": [],
        }

        resp = {
            "request_id": req_id,
            "success": True,
            "actual_parser_id": parser_id,
            "actual_parser_version": runtime_versions.get("docling", "2.0.0"),
            "runtime_versions": runtime_versions,
            "document_ir_dict": doc_ir_dict,
            "warnings": [],
        }
        print(json.dumps(resp), flush=True)

    except Exception as e:
        logger.exception("Docling worker error")
        resp = {
            "request_id": req_data.get("request_id", "req_unknown")
            if "req_data" in locals()
            else "req_unknown",
            "success": False,
            "actual_parser_id": req_data.get("parser_id", "docling_native")
            if "req_data" in locals()
            else "docling_native",
            "actual_parser_version": "2.0.0",
            "runtime_versions": get_runtime_versions(),
            "error_type": "WORKER_PARSE_FAILED",
            "error_message": f"Docling parsing failed: {e!s}",
        }
        print(json.dumps(resp), flush=True)


if __name__ == "__main__":
    main()
