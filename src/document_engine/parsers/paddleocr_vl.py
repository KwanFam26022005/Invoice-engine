"""PaddleOCR-VL visual/layout fallback parser via an isolated local worker."""

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
    "mode": "local_visual_fallback",
    "pipeline_version": "v1.6",
    "device": "cpu",
    "vl_rec_backend": "native",
    "use_doc_orientation_classify": False,
    "use_doc_unwarping": False,
    "use_layout_detection": True,
    "use_chart_recognition": False,
    "use_seal_recognition": False,
    "use_ocr_for_image_block": False,
    "use_queues": False,
}


def _apply_local_model_env(config: dict) -> dict:
    """Resolve explicit local model directories without embedding host paths."""
    resolved = dict(config)
    layout_dir = resolved.get("layout_detection_model_dir") or os.getenv(
        "PADDLE_LAYOUT_MODEL_DIR"
    )
    vl_rec_dir = resolved.get("vl_rec_model_dir") or os.getenv("PADDLE_VL_REC_MODEL_DIR")

    if layout_dir:
        resolved["layout_detection_model_dir"] = layout_dir
    else:
        resolved.pop("layout_detection_model_dir", None)
    if vl_rec_dir:
        resolved["vl_rec_model_dir"] = vl_rec_dir
    else:
        resolved.pop("vl_rec_model_dir", None)
    return resolved


class PaddleOCRVLParser(DocumentParser):
    def __init__(
        self,
        config: Optional[dict] = None,
        worker_client: Optional[WorkerClient] = None,
    ):
        merged_config = _apply_local_model_env({**_PADDLE_DEFAULT_CONFIG, **(config or {})})
        self._spec = ParserSpec(
            parser_id="paddleocr_vl",
            name="PaddleOCR-VL Visual/Layout Fallback Parser",
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
            request = WorkerRequest(
                request_id="req_healthcheck_paddleocr_vl",
                parser_id=self.parser_id,
                operation="healthcheck",
                options=self.spec.config,
                allow_model_download=os.getenv("ALLOW_MODEL_DOWNLOAD") == "1",
            )
            response = self.worker_client.execute_worker(request)
            if response.success and response.health_data:
                return ParserHealth(
                    parser_id=self.parser_id,
                    healthy=True,
                    message=(
                        "PaddleOCR-VL local worker ready "
                        f"({response.health_data.get('python_executable')})"
                    ),
                    dependencies_available=True,
                )
            return ParserHealth(
                parser_id=self.parser_id,
                healthy=False,
                message=response.error_message or "PaddleOCR-VL worker healthcheck failed",
                dependencies_available=bool(
                    response.health_data and response.health_data.get("paddle_installed")
                ),
            )
        except Exception as exc:
            return ParserHealth(
                parser_id=self.parser_id,
                healthy=False,
                message=f"PaddleOCR-VL worker unavailable: {exc}",
                dependencies_available=False,
            )

    def supports(self, profile: DocumentProfile) -> bool:
        return profile.pdf_profile != PDFProfileType.INVALID_PDF

    def parse(
        self, document: SourceDocument, profile: DocumentProfile
    ) -> DocumentParseResult:
        health = self.healthcheck()
        if not health.healthy:
            return DocumentParseResult(
                success=False,
                error_message=f"PaddleOCR-VL fallback unavailable: {health.message}",
            )

        pdf_path = Path(document.path)
        if not pdf_path.exists():
            return DocumentParseResult(
                success=False,
                error_message=f"File not found: {document.path}",
            )

        try:
            request = WorkerRequest(
                request_id=f"req_{document.document_id}_paddleocr_vl",
                parser_id=self.parser_id,
                operation="parse",
                input_path=str(pdf_path),
                document_id=document.document_id,
                source_sha256=document.sha256,
                page_count=document.page_count,
                options=self.spec.config,
                allow_model_download=os.getenv("ALLOW_MODEL_DOWNLOAD") == "1",
            )
            response = self.worker_client.execute_worker(request)
            if not response.success or not response.document_ir_dict:
                return DocumentParseResult(
                    success=False,
                    error_message=response.error_message or "PaddleOCR-VL worker failed",
                )

            document_ir = dict_to_document_ir(response.document_ir_dict, profile)
            return DocumentParseResult(
                success=True,
                document_ir=document_ir,
                warnings=document_ir.warnings,
            )
        except Exception as exc:
            return DocumentParseResult(
                success=False,
                error_message=f"PaddleOCR-VL fallback parse error: {exc}",
            )
