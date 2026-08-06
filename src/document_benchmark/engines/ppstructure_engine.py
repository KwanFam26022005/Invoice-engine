"""PP-StructureV3 engine adapter supporting multipage PDF, configurable OCR, and table recognition."""

from datetime import datetime, timezone
import gc
import importlib.util
import logging
from pathlib import Path
import time
from typing import Any, Dict, List, Optional, Tuple

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


def _check_ppstructure_import() -> Tuple[bool, Optional[str], List[str]]:
    """Check if paddleocr and paddlepaddle are available."""
    missing = []
    if importlib.util.find_spec("paddle") is None:
        missing.append("paddlepaddle")
    if importlib.util.find_spec("paddleocr") is None:
        missing.append("paddleocr")

    if missing:
        return False, f"Missing optional dependencies: {', '.join(missing)}", missing
    return True, None, []


class PPStructureEngine(BaseDocumentEngine):
    """PP-StructureV3 document structure analysis engine adapter."""

    def __init__(self, spec: EngineSpec) -> None:
        super().__init__(spec)
        self.engine_instance = None
        opts = spec.options or {}
        self.language: str = str(opts.get("language", "vi"))
        self.use_general_ocr: bool = bool(opts.get("use_general_ocr", True))
        self.use_table_recognition: bool = bool(opts.get("use_table_recognition", True))
        self.use_formula_recognition: bool = bool(opts.get("use_formula_recognition", False))
        self.use_seal_recognition: bool = bool(opts.get("use_seal_recognition", False))

    def healthcheck(self) -> EngineHealth:
        available, err_msg, missing = _check_ppstructure_import()
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
        available, err_msg, missing = _check_ppstructure_import()
        if not available:
            raise EngineUnavailableError(
                f"Cannot prepare PPStructureEngine: {err_msg}",
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
        except Exception as e:
            raise EngineUnavailableError(
                f"Failed to initialize PPStructure engine: {e}",
                engine_id=self.spec.engine_id,
            ) from e

    def extract(
        self,
        document: DocumentInput,
        target_schema: Optional[Dict[str, Any]] = None,
    ) -> RawExtractionResult:
        if not self._is_prepared or self.engine_instance is None:
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
            # Render PDF pages to numpy images using PyMuPDF (fitz)
            import fitz
            import numpy as np

            doc_pdf = fitz.open(str(pdf_path))
            pages: List[Dict[str, Any]] = []
            tables: List[Dict[str, Any]] = []
            text_parts: List[str] = []

            table_counter = 0
            for page_idx, page in enumerate(doc_pdf):
                page_num = page_idx + 1
                pix = page.get_pixmap(dpi=150)
                img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
                if pix.n == 4:  # RGBA to RGB
                    import cv2

                    img = cv2.cvtColor(img, cv2.COLOR_RGBA2RGB)

                result = self.engine_instance(img)

                page_text_lines = []
                for region in result:
                    r_type = region.get("type", "text")
                    r_res = region.get("res", [])

                    if r_type == "table":
                        table_counter += 1
                        headers, rows = self._parse_pp_table(r_res)
                        tables.append(
                            {
                                "table_index": table_counter - 1,
                                "page_number": page_num,
                                "headers": headers,
                                "rows": rows,
                                "bbox": region.get("bbox"),
                            }
                        )
                    else:
                        if isinstance(r_res, list):
                            for line in r_res:
                                if isinstance(line, dict) and "text" in line:
                                    page_text_lines.append(str(line["text"]))
                                elif isinstance(line, (tuple, list)) and len(line) >= 2:
                                    txt_tuple = line[1]
                                    if isinstance(txt_tuple, (tuple, list)):
                                        page_text_lines.append(str(txt_tuple[0]))

                p_text = "\n".join(page_text_lines)
                text_parts.append(p_text)
                pages.append(
                    {
                        "page_number": page_num,
                        "text": p_text,
                        "width": pix.width,
                        "height": pix.height,
                    }
                )

            doc_pdf.close()

            full_text = "\n\n--- Page Break ---\n\n".join(text_parts)
            field_candidates = self._extract_field_candidates(full_text)

            raw_payload = {
                "engine": "ppstructure_v3",
                "config_id": self.spec.config_id,
                "pages_processed": len(pages),
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

    def _parse_pp_table(self, res: Any) -> Tuple[List[str], List[List[str]]]:
        headers: List[str] = []
        rows: List[List[str]] = []

        if isinstance(res, dict) and "html" in res:
            html = res["html"]
            try:
                from bs4 import BeautifulSoup

                soup = BeautifulSoup(html, "html.parser")
                tr_tags = soup.find_all("tr")
                for tr in tr_tags:
                    cells = [td.get_text(strip=True) for td in tr.find_all(["td", "th"])]
                    if cells:
                        if not headers:
                            headers = cells
                        else:
                            rows.append(cells)
            except Exception:
                pass

        return headers, rows

    def _extract_field_candidates(self, text: str) -> Dict[str, Any]:
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
        self.engine_instance = None
        self._is_prepared = False
        gc.collect()
