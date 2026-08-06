"""Docling adapter for native-text and OCR-enabled benchmark profiles."""

from __future__ import annotations

from datetime import datetime, timezone
import gc
import importlib.util
import logging
import os
from pathlib import Path
import time
from typing import Any

# Avoid Windows PyTorch compiler probing when MSVC is not installed.
os.environ.setdefault("TORCH_COMPILE_DISABLE", "1")

from document_benchmark.core.contracts import (
    DocumentInput,
    EngineHealth,
    EngineSpec,
    RawExtractionResult,
)
from document_benchmark.core.exceptions import EngineUnavailableError
from document_benchmark.core.statuses import EngineStatus
from document_benchmark.engines.base import BaseDocumentEngine
from document_benchmark.engines.runtime import package_version, runtime_identity

logger = logging.getLogger(__name__)


def _check_docling_import() -> tuple[bool, str | None, list[str]]:
    """Check package presence without constructing a converter or loading models."""
    if importlib.util.find_spec("docling") is None:
        return False, "docling package is not installed", ["docling"]
    return True, None, []


class DoclingEngine(BaseDocumentEngine):
    """Docling document extraction adapter with explicit OCR configuration."""

    def __init__(self, spec: EngineSpec) -> None:
        super().__init__(spec)
        self.converter: Any | None = None
        opts = spec.options or {}
        self.do_ocr = bool(opts.get("do_ocr", False))
        self.do_table_structure = bool(opts.get("do_table_structure", True))
        self.generate_picture_images = bool(opts.get("generate_picture_images", False))
        self.ocr_engine = str(opts.get("ocr_engine", "easyocr")).casefold()
        self.ocr_languages = [str(lang) for lang in opts.get("ocr_languages", ["vi", "en"])]
        self.force_full_page_ocr = bool(opts.get("force_full_page_ocr", False))
        self.document_timeout = opts.get("document_timeout_seconds")
        self.benchmark_track = str(
            opts.get("benchmark_track", "scan_ocr" if self.do_ocr else "native_pdf")
        )

    def _runtime_metadata(self) -> dict[str, Any]:
        metadata: dict[str, Any] = {
            "adapter_class": type(self).__qualname__,
            "engine_generation": "Docling",
            "benchmark_track": self.benchmark_track,
            "ocr_enabled": self.do_ocr,
            "ocr_engine": self.ocr_engine if self.do_ocr else None,
            "ocr_languages": self.ocr_languages if self.do_ocr else [],
            "package_versions": {
                "docling": package_version("docling"),
                "docling-core": package_version("docling-core"),
            },
        }
        if self.converter is not None:
            metadata.update(runtime_identity(self.converter))
        return metadata

    def healthcheck(self) -> EngineHealth:
        available, error_message, missing = _check_docling_import()
        if not available:
            return EngineHealth(
                engine_id=self.spec.engine_id,
                config_id=self.spec.config_id,
                status=EngineStatus.UNAVAILABLE,
                available=False,
                error_message=error_message,
                missing_dependencies=missing,
                runtime_metadata=self._runtime_metadata(),
            )
        if not self.spec.enabled:
            return EngineHealth(
                engine_id=self.spec.engine_id,
                config_id=self.spec.config_id,
                status=EngineStatus.UNAVAILABLE,
                available=False,
                error_message="Config is disabled",
                runtime_metadata=self._runtime_metadata(),
            )
        if self.do_ocr and self.ocr_engine not in {"easyocr", "auto"}:
            return EngineHealth(
                engine_id=self.spec.engine_id,
                config_id=self.spec.config_id,
                status=EngineStatus.UNAVAILABLE,
                available=False,
                error_message=f"Unsupported Docling OCR engine: {self.ocr_engine}",
                runtime_metadata=self._runtime_metadata(),
            )
        return EngineHealth(
            engine_id=self.spec.engine_id,
            config_id=self.spec.config_id,
            status=EngineStatus.SUCCESS,
            available=True,
            runtime_metadata=self._runtime_metadata(),
        )

    def prepare(self) -> None:
        available, error_message, missing = _check_docling_import()
        if not available:
            raise EngineUnavailableError(
                f"Cannot prepare DoclingEngine: {error_message}",
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
            if self.document_timeout is not None and hasattr(
                pipeline_options, "document_timeout"
            ):
                pipeline_options.document_timeout = float(self.document_timeout)

            if self.do_ocr:
                if self.ocr_engine == "easyocr":
                    from docling.datamodel.pipeline_options import EasyOcrOptions

                    pipeline_options.ocr_options = EasyOcrOptions(
                        lang=self.ocr_languages,
                        use_gpu=self.spec.device.casefold() in {"gpu", "cuda"},
                        force_full_page_ocr=self.force_full_page_ocr,
                    )
                elif self.ocr_engine == "auto":
                    from docling.datamodel.pipeline_options import OcrAutoOptions

                    pipeline_options.ocr_options = OcrAutoOptions(
                        lang=[],
                        force_full_page_ocr=self.force_full_page_ocr,
                    )

            self.converter = DocumentConverter(
                format_options={
                    InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options)
                }
            )
            self._is_prepared = True
        except Exception as exc:
            raise EngineUnavailableError(
                f"Failed to initialize Docling converter: {exc}",
                engine_id=self.spec.engine_id,
            ) from exc

    def extract(
        self,
        document: DocumentInput,
        target_schema: dict[str, Any] | None = None,
    ) -> RawExtractionResult:
        del target_schema
        if not self._is_prepared or self.converter is None:
            self.prepare()

        started_at = datetime.now(timezone.utc)
        started = time.perf_counter()
        pdf_path = Path(document.path)
        if not pdf_path.exists():
            return self._failure_result(
                document,
                started_at,
                started,
                "FileNotFoundError",
                f"PDF document not found: {document.path}",
            )

        try:
            conversion = self.converter.convert(str(pdf_path))
            doc_obj = conversion.document
            full_text = doc_obj.export_to_markdown()

            pages: list[dict[str, Any]] = []
            doc_pages = getattr(doc_obj, "pages", None)
            if doc_pages:
                for page_no, page_item in doc_pages.items():
                    size = getattr(page_item, "size", None)
                    pages.append(
                        {
                            "page_number": page_no,
                            "size": {
                                "width": getattr(size, "width", 0.0),
                                "height": getattr(size, "height", 0.0),
                            },
                        }
                    )
            else:
                pages = [
                    {"page_number": page_no, "size": {"width": 0.0, "height": 0.0}}
                    for page_no in range(1, document.page_count + 1)
                ]

            tables = [
                self._parse_docling_table(index, table)
                for index, table in enumerate(getattr(doc_obj, "tables", []) or [])
            ]
            warnings: list[str] = []
            if document.metadata.get("is_image_only_pdf") and not self.do_ocr:
                warnings.append("Image-only PDF processed with OCR disabled")

            runtime_metadata = self._runtime_metadata()
            raw_payload = {
                "engine": "docling",
                "config_id": self.spec.config_id,
                "benchmark_track": self.benchmark_track,
                "runtime_metadata": runtime_metadata,
                "markdown": full_text,
                "table_count": len(tables),
            }
            completed_at = datetime.now(timezone.utc)
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
                field_candidates=self._extract_field_candidates(full_text),
                warnings=warnings,
                started_at=started_at,
                completed_at=completed_at,
                execution_time_ms=(time.perf_counter() - started) * 1000.0,
            )
        except Exception as exc:
            return self._failure_result(
                document,
                started_at,
                started,
                type(exc).__name__,
                str(exc),
            )

    def _failure_result(
        self,
        document: DocumentInput,
        started_at: datetime,
        started: float,
        error_type: str,
        error_message: str,
    ) -> RawExtractionResult:
        return RawExtractionResult(
            run_id="",
            document_id=document.document_id,
            engine_id=self.spec.engine_id,
            config_id=self.spec.config_id,
            output_kind=self.spec.output_kind,
            success=False,
            error_type=error_type,
            error_message=error_message,
            raw_payload={"runtime_metadata": self._runtime_metadata()},
            started_at=started_at,
            completed_at=datetime.now(timezone.utc),
            execution_time_ms=(time.perf_counter() - started) * 1000.0,
        )

    @staticmethod
    def _parse_docling_table(index: int, table: Any) -> dict[str, Any]:
        headers: list[str] = []
        rows: list[list[str]] = []
        try:
            dataframe = table.export_to_dataframe()
            headers = [str(column) for column in dataframe.columns]
            rows = [[str(value) for value in row.values] for _, row in dataframe.iterrows()]
        except Exception:
            logger.debug("Docling table dataframe export failed", exc_info=True)

        page_number = 1
        provenance = getattr(table, "prov", None)
        if provenance:
            page_number = getattr(provenance[0], "page_no", 1)
        return {
            "table_index": index,
            "page_number": page_number,
            "headers": headers,
            "rows": rows,
        }

    @staticmethod
    def _extract_field_candidates(text: str) -> dict[str, Any]:
        import re

        candidates: dict[str, Any] = {}
        patterns = {
            "invoice_number": r"(?:Số|No|Invoice\s*No)[.:\s]*([A-Z0-9\-\/]{4,20})",
            "invoice_series": r"(?:Ký\s*hiệu|Series)[.:\s]*([A-Z0-9]{4,10})",
            "invoice_date": r"(?:Ngày|Date)[.:\s]*(\d{1,2}[\/\-\.]\d{1,2}[\/\-\.]\d{4})",
            "seller_tax_id": r"(?:Mã\s*số\s*thuế|MST)[.:\s]*([0-9]{10}(?:-[0-9]{3})?)",
            "total_amount": r"(?:Tổng\s*cộng|Tổng\s*tiền|Total)[.:\s]*([0-9\.,]{4,20})",
        }
        for field, pattern in patterns.items():
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                candidates[field] = match.group(1).strip()
        return candidates

    def close(self) -> None:
        self.converter = None
        self._is_prepared = False
        gc.collect()
