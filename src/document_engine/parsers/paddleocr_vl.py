"""PaddleOCR-VL fallback parser adapter for difficult, irregular, or failed layout documents via isolated worker."""

import os
from pathlib import Path
from typing import Optional

from document_engine.core.models import PDFProfileType
from document_engine.ir.models import (
    DocumentParseResult,
    DocumentProfile,
    SourceDocument,
)
from document_engine.parsers.base import DocumentParser, ParserHealth, ParserSpec
from document_engine.parsers.docling_native import dict_to_document_ir
from document_engine.runtime import WorkerClient, WorkerRequest


_PADDLE_DEFAULT_CONFIG: dict = {
    "mode": "local_fallback",
    "pipeline_version": "v1.6",
    "device": "cpu",
    "engine": "paddle",
    "use_doc_orientation_classify": False,
    "use_doc_unwarping": False,
    "use_layout_detection": True,
    "use_chart_recognition": False,
    "use_seal_recognition": False,
    "use_ocr_for_image_block": False,
}


class PaddleOCRVLParser(DocumentParser):
    def __init__(
        self,
        config: Optional[dict] = None,
        worker_client: Optional[WorkerClient] = None,
    ):
        merged_config = {**_PADDLE_DEFAULT_CONFIG, **(config or {})}
        self._spec = ParserSpec(
            parser_id="paddleocr_vl",
            name="PaddleOCR-VL Fallback Parser",
            version="3.0.0",
            supported_profiles=[
                PDFProfileType.NATIVE_PDF,
                PDFProfileType.SCAN_PDF,
                PDFProfileType.MIXED_PDF,
            ],
            requires_gpu=False,
            is_fallback=True,
            config=merged_config,
        )
        self.worker_client = worker_client or WorkerClient()

    @property
    def spec(self) -> ParserSpec:
        return self._spec

    def healthcheck(self) -> ParserHealth:
        try:
            req = WorkerRequest(
                request_id="req_healthcheck_paddleocr_vl",
                parser_id=self.parser_id,
                operation="healthcheck",
                options=self.spec.config,
                allow_model_download=os.getenv("ALLOW_MODEL_DOWNLOAD") == "1",
            )
            resp = self.worker_client.execute_worker(req)
            if resp.success and resp.health_data:
                return ParserHealth(
                    parser_id=self.parser_id,
                    healthy=True,
                    message=f"PaddleOCR-VL worker ready ({resp.health_data.get('python_executable')})",
                    dependencies_available=True,
                )
            return ParserHealth(
                parser_id=self.parser_id,
                healthy=False,
                message=resp.error_message or "PaddleOCR-VL worker healthcheck failed",
                dependencies_available=bool(resp.health_data and resp.health_data.get("paddle_installed")),
            )
        except Exception as e:
            return ParserHealth(
                parser_id=self.parser_id,
                healthy=False,
                message=f"PaddleOCR-VL worker unavailable: {e}",
                dependencies_available=False,
            )

    def supports(self, profile: DocumentProfile) -> bool:
        return profile.pdf_profile != PDFProfileType.INVALID_PDF

    def parse(self, document: SourceDocument, profile: DocumentProfile) -> DocumentParseResult:
        health = self.healthcheck()
        if not health.healthy:
            return DocumentParseResult(
                success=False,
                error_message=f"PaddleOCR-VL fallback unavailable: {health.message}",
            )

        pdf_path = Path(document.path)
        if not pdf_path.exists():
            return DocumentParseResult(
                success=False, error_message=f"File not found: {document.path}"
            )

        try:
            request = WorkerRequest(
                request_id=f"req_{document.document_id}_paddleocr_vl",
                parser_id=self.parser_id,
                operation="parse",
                input_path=str(pdf_path),
                document_id=document.document_id,
                page_count=document.page_count,
                options=self.spec.config,
                allow_model_download=os.getenv("ALLOW_MODEL_DOWNLOAD") == "1",
            )

            resp = self.worker_client.execute_worker(request)

            if not resp.success or not resp.document_ir_dict:
                return DocumentParseResult(
                    success=False,
                    error_message=resp.error_message or "PaddleOCR-VL worker failed",
                )

            doc_ir = dict_to_document_ir(resp.document_ir_dict, profile)
            return DocumentParseResult(
                success=True, document_ir=doc_ir, warnings=doc_ir.warnings
            )

        except Exception as e:
            return DocumentParseResult(
                success=False, error_message=f"PaddleOCR-VL fallback parse error: {e}"
            )
