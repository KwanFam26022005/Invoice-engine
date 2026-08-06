"""Docling engine adapter supporting text-only and text-and-table extraction profiles."""

from datetime import datetime, timezone
import gc
import logging
import os
from pathlib import Path
import time
from typing import Any, Dict, List, Optional, Tuple

# Prevent PyTorch Inductor compilation error on Windows when MSVC cl compiler is not installed
os.environ["TORCH_COMPILE_DISABLE"] = "1"

from document_benchmark.core.contracts import (
    DocumentInput,
    EngineHealth,
    EngineSpec,
    RawExtractionResult,
)
from document_benchmark.core.exceptions import EngineUnavailableError
from document_benchmark.core.statuses import EngineStatus
from document_benchmark.engines.base import BaseDocumentEngine

logger = logging.getLogger(__name__)


def _check_docling_import() -> Tuple[bool, Optional[str], List[str]]:
    """Check if docling library and dependencies are available."""
    try:
        import importlib.util

        if importlib.util.find_spec("docling") is not None:
            return True, None, []
        return False, "docling package is not installed", ["docling"]
    except Exception as e:
        return False, f"Error checking docling: {e}", ["docling"]


class DoclingEngine(BaseDocumentEngine):
    """Docling document extraction engine adapter."""

    def __init__(self, spec: EngineSpec) -> None:
        super().__init__(spec)
        self.converter = None
        opts = spec.options or {}
        self.do_ocr: bool = bool(opts.get("do_ocr", False))
        self.do_table_structure: bool = bool(opts.get("do_table_structure", True))
        self.generate_picture_images: bool = bool(opts.get("generate_picture_images", False))

    def healthcheck(self) -> EngineHealth:
        available, err_msg, missing = _check_docling_import()
        if not available:
            return EngineHealth(
                engine_id=self.spec.engine_id,
                config_id=self.spec.config_id,
                status=EngineStatus.UNAVAILABLE,
                available=False,
                error_message=err_msg,
                missing_dependencies=missing,
            )

        if not self.spec.enabled:
            return EngineHealth(
                engine_id=self.spec.engine_id,
                config_id=self.spec.config_id,
                status=EngineStatus.UNAVAILABLE,
                available=False,
                error_message="Config is disabled",
            )

        return EngineHealth(
            engine_id=self.spec.engine_id,
            config_id=self.spec.config_id,
            status=EngineStatus.SUCCESS,
            available=True,
        )

    def prepare(self) -> None:
        available, err_msg, missing = _check_docling_import()
        if not available:
            raise EngineUnavailableError(
                f"Cannot prepare DoclingEngine: {err_msg}",
                engine_id=self.spec.engine_id,
                details={"missing": missing},
            )

        try:
            from docling.datamodel.base_models import InputFormat
            from docling.datamodel.pipeline_options import PdfPipelineOptions
            from docling.document_converter import DocumentConverter, PdfFormatOption

            pipeline_options = PdfPipelineOptions()
            pipeline_options.do_ocr = self.do_ocr
            pipeline_options.do_table_structure = self.do_table_structure
            pipeline_options.generate_page_images = False
            pipeline_options.generate_picture_images = self.generate_picture_images

            self.converter = DocumentConverter(
                format_options={
                    InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options)
                }
            )
            self._is_prepared = True
        except Exception as e:
            raise EngineUnavailableError(
                f"Failed to initialize Docling converter: {e}",
                engine_id=self.spec.engine_id,
            ) from e

    def extract(
        self,
        document: DocumentInput,
        target_schema: Optional[Dict[str, Any]] = None,
    ) -> RawExtractionResult:
        if not self._is_prepared or self.converter is None:
            self.prepare()

        started_at = datetime.now(timezone.utc)
        start_t = time.perf_counter()

        pdf_path = Path(document.path)
        if not pdf_path.exists():
            exec_time = (time.perf_counter() - start_t) * 1000.0
            return RawExtractionResult(
                run_id="",
                document_id=document.document_id,
                engine_id=self.spec.engine_id,
                config_id=self.spec.config_id,
                output_kind=self.spec.output_kind,
                success=False,
                error_type="FileNotFoundError",
                error_message=f"PDF document not found: {document.path}",
                started_at=started_at,
                completed_at=datetime.now(timezone.utc),
                execution_time_ms=exec_time,
            )

        try:
            conv_result = self.converter.convert(str(pdf_path))
            doc_obj = conv_result.document

            full_text = doc_obj.export_to_markdown()

            pages: List[Dict[str, Any]] = []
            if hasattr(doc_obj, "pages") and doc_obj.pages:
                for page_no, page_item in doc_obj.pages.items():
                    pages.append(
                        {
                            "page_number": page_no,
                            "size": {
                                "width": getattr(page_item.size, "width", 0.0),
                                "height": getattr(page_item.size, "height", 0.0),
                            },
                        }
                    )
            else:
                for p in range(1, document.page_count + 1):
                    pages.append({"page_number": p, "size": {"width": 595.0, "height": 842.0}})

            tables: List[Dict[str, Any]] = []
            if hasattr(doc_obj, "tables") and doc_obj.tables:
                for idx, tbl in enumerate(doc_obj.tables):
                    tbl_dict = self._parse_docling_table(idx, tbl)
                    tables.append(tbl_dict)

            field_candidates = self._extract_field_candidates(full_text)

            raw_payload = {
                "engine": "docling",
                "config_id": self.spec.config_id,
                "markdown": full_text,
                "table_count": len(tables),
            }

            completed_at = datetime.now(timezone.utc)
            exec_time = (time.perf_counter() - start_t) * 1000.0

            return RawExtractionResult(
                run_id="",
                document_id=document.document_id,
                engine_id=self.spec.engine_id,
                config_id=self.spec.config_id,
                output_kind=self.spec.output_kind,
                success=True,
                raw_payload=raw_payload,
                full_text=full_text,
                pages=pages,
                tables=tables,
                field_candidates=field_candidates,
                warnings=[],
                started_at=started_at,
                completed_at=completed_at,
                execution_time_ms=exec_time,
            )

        except Exception as e:
            completed_at = datetime.now(timezone.utc)
            exec_time = (time.perf_counter() - start_t) * 1000.0
            return RawExtractionResult(
                run_id="",
                document_id=document.document_id,
                engine_id=self.spec.engine_id,
                config_id=self.spec.config_id,
                output_kind=self.spec.output_kind,
                success=False,
                error_type=type(e).__name__,
                error_message=str(e),
                started_at=started_at,
                completed_at=completed_at,
                execution_time_ms=exec_time,
            )

    def _parse_docling_table(self, idx: int, tbl: Any) -> Dict[str, Any]:
        headers: List[str] = []
        rows: List[List[str]] = []

        try:
            df = tbl.export_to_dataframe()
            headers = [str(c) for c in df.columns]
            for _, r in df.iterrows():
                rows.append([str(val) for val in r.values])
        except Exception:
            pass

        page_no = 1
        if hasattr(tbl, "prov") and tbl.prov:
            page_no = getattr(tbl.prov[0], "page_no", 1)

        return {
            "table_index": idx,
            "page_number": page_no,
            "headers": headers,
            "rows": rows,
        }

    def _extract_field_candidates(self, text: str) -> Dict[str, Any]:
        """Extract candidate key-value pairs from text regex heuristics."""
        import re

        candidates: Dict[str, Any] = {}

        patterns = {
            "invoice_number": r"(?:Số|No|Invoice\s*No)[.:\s]*([A-Z0-9\-\/]{4,20})",
            "invoice_series": r"(?:Ký\s*hiệu|Series)[.:\s]*([A-Z0-9]{4,10})",
            "invoice_date": r"(?:Ngày|Date)[.:\s]*(\d{1,2}[\/\-\.]\d{1,2}[\/\-\.]\d{4})",
            "seller_tax_id": r"(?:Mã\s*số\s*thuế|MST)[.:\s]*([0-9]{10}(?:-[0-9]{3})?)",
            "total_amount": r"(?:Tổng\s*cộng|Tổng\s*tiền|Total)[.:\s]*([0-9\.,]{4,20})",
        }

        for field, pat in patterns.items():
            m = re.search(pat, text, re.IGNORECASE)
            if m:
                candidates[field] = m.group(1).strip()

        return candidates

    def close(self) -> None:
        self.converter = None
        self._is_prepared = False
        gc.collect()
