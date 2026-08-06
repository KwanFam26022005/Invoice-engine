"""Local PP-StructureV3 adapter using the PaddleOCR 3.x pipeline API."""

from __future__ import annotations

from datetime import datetime, timezone
import gc
import importlib
import importlib.util
import logging
from pathlib import Path
import time
from typing import Any

from document_benchmark.core.contracts import (
    DocumentInput,
    EngineHealth,
    EngineSpec,
    RawExtractionResult,
)
from document_benchmark.core.exceptions import EngineUnavailableError
from document_benchmark.core.statuses import EngineStatus
from document_benchmark.engines.base import BaseDocumentEngine
from document_benchmark.engines.runtime import json_safe, package_version, runtime_identity

logger = logging.getLogger(__name__)


def _check_ppstructure_v3_import() -> tuple[bool, str | None, list[str]]:
    """Check PaddleOCR 3.x dependencies and the PPStructureV3 public symbol."""
    missing: list[str] = []
    if importlib.util.find_spec("paddle") is None:
        missing.append("paddlepaddle>=3.0")
    if importlib.util.find_spec("paddleocr") is None:
        missing.append("paddleocr>=3.0")
    if missing:
        return False, f"Missing optional dependencies: {', '.join(missing)}", missing

    try:
        paddleocr_module = importlib.import_module("paddleocr")
    except Exception as exc:
        return False, f"Unable to import paddleocr: {exc}", ["paddleocr>=3.0"]
    if not hasattr(paddleocr_module, "PPStructureV3"):
        return (
            False,
            "Installed paddleocr does not expose PPStructureV3; install PaddleOCR 3.x",
            ["paddleocr>=3.0"],
        )
    return True, None, []


# Compatibility alias retained for callers that imported the original class name.
def _check_ppstructure_import() -> tuple[bool, str | None, list[str]]:
    return _check_ppstructure_v3_import()


class PPStructureV3Engine(BaseDocumentEngine):
    """PP-StructureV3 pipeline adapter preserving page JSON and Markdown output."""

    def __init__(self, spec: EngineSpec) -> None:
        super().__init__(spec)
        self.pipeline: Any | None = None
        options = spec.options or {}
        self.language = str(options.get("language", "vi"))
        self.use_doc_orientation_classify = bool(
            options.get("use_doc_orientation_classify", False)
        )
        self.use_doc_unwarping = bool(options.get("use_doc_unwarping", False))
        self.use_textline_orientation = bool(options.get("use_textline_orientation", False))
        self.use_table_recognition = bool(options.get("use_table_recognition", True))
        self.use_formula_recognition = bool(options.get("use_formula_recognition", False))
        self.use_chart_recognition = bool(options.get("use_chart_recognition", False))
        self.use_seal_recognition = bool(options.get("use_seal_recognition", False))
        self.inference_engine = options.get("inference_engine")
        self.benchmark_track = str(options.get("benchmark_track", "scan_ocr"))

    def _runtime_metadata(self) -> dict[str, Any]:
        metadata: dict[str, Any] = {
            "adapter_class": type(self).__qualname__,
            "engine_generation": "PP-StructureV3",
            "benchmark_track": self.benchmark_track,
            "package_versions": {
                "paddleocr": package_version("paddleocr"),
                "paddlepaddle": package_version("paddlepaddle"),
            },
        }
        if self.pipeline is not None:
            metadata.update(runtime_identity(self.pipeline))
        return metadata

    def healthcheck(self) -> EngineHealth:
        available, error_message, missing = _check_ppstructure_v3_import()
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
        return EngineHealth(
            engine_id=self.spec.engine_id,
            config_id=self.spec.config_id,
            status=EngineStatus.SUCCESS,
            available=True,
            runtime_metadata=self._runtime_metadata(),
        )

    def prepare(self) -> None:
        available, error_message, missing = _check_ppstructure_v3_import()
        if not available:
            raise EngineUnavailableError(
                f"Cannot prepare PPStructureV3Engine: {error_message}",
                engine_id=self.spec.engine_id,
                details={"missing": missing},
            )

        try:
            from paddleocr import PPStructureV3

            kwargs: dict[str, Any] = {
                "lang": self.language,
                "device": self.spec.device,
                "use_doc_orientation_classify": self.use_doc_orientation_classify,
                "use_doc_unwarping": self.use_doc_unwarping,
                "use_textline_orientation": self.use_textline_orientation,
                "use_table_recognition": self.use_table_recognition,
                "use_formula_recognition": self.use_formula_recognition,
                "use_chart_recognition": self.use_chart_recognition,
                "use_seal_recognition": self.use_seal_recognition,
            }
            if self.inference_engine:
                kwargs["engine"] = self.inference_engine
            self.pipeline = PPStructureV3(**kwargs)
            self._is_prepared = True
        except Exception as exc:
            raise EngineUnavailableError(
                f"Failed to initialize PP-StructureV3: {exc}",
                engine_id=self.spec.engine_id,
            ) from exc

    def extract(
        self,
        document: DocumentInput,
        target_schema: dict[str, Any] | None = None,
    ) -> RawExtractionResult:
        del target_schema
        if not self._is_prepared or self.pipeline is None:
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
            page_results: list[dict[str, Any]] = []
            markdown_payloads: list[dict[str, Any]] = []
            pages: list[dict[str, Any]] = []
            tables: list[dict[str, Any]] = []
            text_parts: list[str] = []

            output = self.pipeline.predict(input=str(pdf_path))
            for fallback_index, result in enumerate(output):
                result_json = json_safe(getattr(result, "json", {}))
                markdown_info = json_safe(getattr(result, "markdown", {}))
                if not isinstance(result_json, dict):
                    result_json = {"result": result_json}
                if not isinstance(markdown_info, dict):
                    markdown_info = {"markdown_texts": str(markdown_info)}

                page_number = self._page_number(result_json, fallback_index + 1)
                page_text = self._markdown_text(markdown_info)
                if page_text:
                    text_parts.append(page_text)
                markdown_payloads.append(markdown_info)
                page_results.append(result_json)
                pages.append(
                    {
                        "page_number": page_number,
                        "text": page_text,
                        "structured_result": result_json,
                    }
                )
                tables.extend(self._collect_tables(result_json, page_number))

            full_text = self._concatenate_markdown(markdown_payloads, text_parts)
            warnings: list[str] = []
            if not page_results:
                warnings.append("PP-StructureV3 returned no page results")

            raw_payload = {
                "engine": "ppstructure_v3",
                "config_id": self.spec.config_id,
                "benchmark_track": self.benchmark_track,
                "runtime_metadata": self._runtime_metadata(),
                "pages_processed": len(pages),
                "table_count": len(tables),
                "page_results": page_results,
            }
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
                completed_at=datetime.now(timezone.utc),
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

    def _concatenate_markdown(
        self,
        markdown_payloads: list[dict[str, Any]],
        fallback_texts: list[str],
    ) -> str:
        if markdown_payloads and hasattr(self.pipeline, "concatenate_markdown_pages"):
            try:
                merged = self.pipeline.concatenate_markdown_pages(markdown_payloads)
                if isinstance(merged, str):
                    return merged
            except Exception:
                logger.debug("PP-StructureV3 markdown concatenation failed", exc_info=True)
        return "\n\n--- Page Break ---\n\n".join(fallback_texts)

    @staticmethod
    def _markdown_text(markdown_info: dict[str, Any]) -> str:
        value = markdown_info.get("markdown_texts", "")
        if isinstance(value, str):
            return value
        if isinstance(value, list):
            return "\n".join(str(item) for item in value)
        return str(value) if value else ""

    @staticmethod
    def _page_number(result_json: dict[str, Any], fallback: int) -> int:
        candidates = [result_json, result_json.get("res", {})]
        for candidate in candidates:
            if isinstance(candidate, dict):
                page_index = candidate.get("page_index")
                if isinstance(page_index, int):
                    return page_index + 1
        return fallback

    @classmethod
    def _collect_tables(cls, value: Any, page_number: int) -> list[dict[str, Any]]:
        tables: list[dict[str, Any]] = []
        table_keys = {
            "table_res_list",
            "table_results",
            "table_res",
            "tables",
            "table_result",
        }

        def visit(node: Any, path: str) -> None:
            if isinstance(node, dict):
                for key, item in node.items():
                    child_path = f"{path}.{key}" if path else str(key)
                    if str(key).casefold() in table_keys:
                        payloads = item if isinstance(item, list) else [item]
                        for payload in payloads:
                            tables.append(
                                {
                                    "table_index": len(tables),
                                    "page_number": page_number,
                                    "source_path": child_path,
                                    "raw": json_safe(payload),
                                }
                            )
                    else:
                        visit(item, child_path)
            elif isinstance(node, list):
                for index, item in enumerate(node):
                    visit(item, f"{path}[{index}]")

        visit(value, "")
        return tables

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
        self.pipeline = None
        self._is_prepared = False
        gc.collect()


# Backward-compatible import name; it now points to the genuine V3 adapter.
PPStructureEngine = PPStructureV3Engine
