"""Legacy PP-StructureV2 adapter retained for explicitly labelled comparisons."""

from __future__ import annotations

from datetime import datetime, timezone
import gc
import importlib
import importlib.util
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
from document_benchmark.engines.runtime import package_version, runtime_identity


def _check_ppstructure_v2_import() -> tuple[bool, str | None, list[str]]:
    missing: list[str] = []
    if importlib.util.find_spec("paddle") is None:
        missing.append("paddlepaddle<3")
    if importlib.util.find_spec("paddleocr") is None:
        missing.append("paddleocr<3")
    if missing:
        return False, f"Missing optional dependencies: {', '.join(missing)}", missing
    try:
        module = importlib.import_module("paddleocr")
    except Exception as exc:
        return False, f"Unable to import paddleocr: {exc}", ["paddleocr<3"]
    if not hasattr(module, "PPStructure"):
        return (
            False,
            "Installed paddleocr does not expose the legacy PPStructure symbol",
            ["paddleocr>=2.7,<3"],
        )
    return True, None, []


class PPStructureV2LegacyEngine(BaseDocumentEngine):
    """Explicitly labelled wrapper around the PaddleOCR 2.x PPStructure API."""

    def __init__(self, spec: EngineSpec) -> None:
        super().__init__(spec)
        self.engine_instance: Any | None = None
        options = spec.options or {}
        self.language = str(options.get("language", "vi"))
        self.use_general_ocr = bool(options.get("use_general_ocr", True))
        self.use_table_recognition = bool(options.get("use_table_recognition", True))
        self.render_dpi = int(options.get("render_dpi", 150))
        self.benchmark_track = str(options.get("benchmark_track", "scan_ocr"))

    def _runtime_metadata(self) -> dict[str, Any]:
        metadata: dict[str, Any] = {
            "adapter_class": type(self).__qualname__,
            "engine_generation": "PP-StructureV2 legacy",
            "benchmark_track": self.benchmark_track,
            "package_versions": {
                "paddleocr": package_version("paddleocr"),
                "paddlepaddle": package_version("paddlepaddle"),
            },
        }
        if self.engine_instance is not None:
            metadata.update(runtime_identity(self.engine_instance))
        return metadata

    def healthcheck(self) -> EngineHealth:
        available, error_message, missing = _check_ppstructure_v2_import()
        if not available or not self.spec.enabled:
            return EngineHealth(
                engine_id=self.spec.engine_id,
                config_id=self.spec.config_id,
                status=EngineStatus.UNAVAILABLE,
                available=False,
                error_message=error_message or "Config is disabled",
                missing_dependencies=missing,
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
        available, error_message, missing = _check_ppstructure_v2_import()
        if not available:
            raise EngineUnavailableError(
                f"Cannot prepare PPStructureV2LegacyEngine: {error_message}",
                engine_id=self.spec.engine_id,
                details={"missing": missing},
            )
        try:
            from paddleocr import PPStructure

            self.engine_instance = PPStructure(
                show_log=False,
                lang=self.language,
                ocr=self.use_general_ocr,
                table=self.use_table_recognition,
                recovery=True,
                structure_version="PP-StructureV2",
            )
            self._is_prepared = True
        except Exception as exc:
            raise EngineUnavailableError(
                f"Failed to initialize legacy PP-StructureV2: {exc}",
                engine_id=self.spec.engine_id,
            ) from exc

    def extract(
        self,
        document: DocumentInput,
        target_schema: dict[str, Any] | None = None,
    ) -> RawExtractionResult:
        del target_schema
        if not self._is_prepared or self.engine_instance is None:
            self.prepare()

        started_at = datetime.now(timezone.utc)
        started = time.perf_counter()
        pdf_path = Path(document.path)
        if not pdf_path.exists():
            return self._failure(document, started_at, started, "FileNotFoundError", str(pdf_path))

        try:
            import fitz
            import numpy as np

            pages: list[dict[str, Any]] = []
            tables: list[dict[str, Any]] = []
            text_parts: list[str] = []
            with fitz.open(pdf_path) as pdf:
                for page_index, page in enumerate(pdf):
                    pixmap = page.get_pixmap(dpi=self.render_dpi, alpha=False)
                    image = np.frombuffer(pixmap.samples, dtype=np.uint8).reshape(
                        pixmap.height, pixmap.width, pixmap.n
                    )
                    regions = self.engine_instance(image)
                    page_text: list[str] = []
                    for region in regions:
                        region_type = region.get("type", "text")
                        result = region.get("res", [])
                        if region_type == "table":
                            tables.append(
                                {
                                    "table_index": len(tables),
                                    "page_number": page_index + 1,
                                    "bbox": region.get("bbox"),
                                    "raw": result,
                                }
                            )
                        elif isinstance(result, list):
                            for line in result:
                                if isinstance(line, dict) and "text" in line:
                                    page_text.append(str(line["text"]))
                                elif isinstance(line, (list, tuple)) and len(line) >= 2:
                                    candidate = line[1]
                                    if isinstance(candidate, (list, tuple)) and candidate:
                                        page_text.append(str(candidate[0]))
                    text = "\n".join(page_text)
                    text_parts.append(text)
                    pages.append(
                        {
                            "page_number": page_index + 1,
                            "text": text,
                            "width": pixmap.width,
                            "height": pixmap.height,
                        }
                    )

            full_text = "\n\n--- Page Break ---\n\n".join(text_parts)
            return RawExtractionResult(
                run_id="",
                document_id=document.document_id,
                engine_id=self.spec.engine_id,
                config_id=self.spec.config_id,
                output_kind=self.spec.output_kind,
                success=True,
                raw_payload={
                    "engine": "ppstructure_v2_legacy",
                    "config_id": self.spec.config_id,
                    "benchmark_track": self.benchmark_track,
                    "runtime_metadata": self._runtime_metadata(),
                    "pages_processed": len(pages),
                    "table_count": len(tables),
                },
                full_text=full_text,
                pages=pages,
                tables=tables,
                started_at=started_at,
                completed_at=datetime.now(timezone.utc),
                execution_time_ms=(time.perf_counter() - started) * 1000.0,
            )
        except Exception as exc:
            return self._failure(document, started_at, started, type(exc).__name__, str(exc))

    def _failure(
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

    def close(self) -> None:
        self.engine_instance = None
        self._is_prepared = False
        gc.collect()
