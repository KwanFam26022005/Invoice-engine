"""Docling OCR parser adapter for scanned & image-only PDFs via isolated worker."""

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


_DOCLING_OCR_DEFAULT_CONFIG: dict = {
    "do_ocr": True,
    "ocr_engine": "easyocr",
    "ocr_languages": ["vi", "en"],
    "do_table_structure": True,
}


class DoclingOCRParser(DocumentParser):
    def __init__(
        self,
        config: Optional[dict] = None,
        worker_client: Optional[WorkerClient] = None,
    ):
        merged_config = {**_DOCLING_OCR_DEFAULT_CONFIG, **(config or {})}
        self._spec = ParserSpec(
            parser_id="docling_ocr",
            name="Docling OCR Parser (EasyOCR vi/en)",
            version="2.0.0",
            supported_profiles=[
                PDFProfileType.SCAN_PDF,
                PDFProfileType.MIXED_PDF,
                PDFProfileType.NATIVE_PDF,
            ],
            requires_gpu=False,
            is_fallback=False,
            config=merged_config,
        )
        self.worker_client = worker_client or WorkerClient()

    @property
    def spec(self) -> ParserSpec:
        return self._spec

    def healthcheck(self) -> ParserHealth:
        try:
            req = WorkerRequest(
                request_id="req_healthcheck_docling_ocr",
                parser_id=self.parser_id,
                operation="healthcheck",
                allow_model_download=os.getenv("ALLOW_MODEL_DOWNLOAD") == "1",
            )
            resp = self.worker_client.execute_worker(req)
            if resp.success and resp.health_data:
                return ParserHealth(
                    parser_id=self.parser_id,
                    healthy=True,
                    message=f"Docling OCR worker ready ({resp.health_data.get('python_executable')})",
                    dependencies_available=True,
                )
            return ParserHealth(
                parser_id=self.parser_id,
                healthy=False,
                message=resp.error_message or "Docling OCR worker healthcheck failed",
                dependencies_available=bool(
                    resp.health_data
                    and resp.health_data.get("docling_installed")
                    and resp.health_data.get("easyocr_installed")
                ),
            )
        except Exception as e:
            return ParserHealth(
                parser_id=self.parser_id,
                healthy=False,
                message=f"Docling OCR worker unavailable: {e}",
                dependencies_available=False,
            )

    def supports(self, profile: DocumentProfile) -> bool:
        return profile.pdf_profile in (
            PDFProfileType.SCAN_PDF,
            PDFProfileType.MIXED_PDF,
            PDFProfileType.NATIVE_PDF,
        )

    def parse(self, document: SourceDocument, profile: DocumentProfile) -> DocumentParseResult:
        health = self.healthcheck()
        if not health.healthy:
            return DocumentParseResult(
                success=False,
                error_message=f"Docling OCR unavailable: {health.message}",
            )

        pdf_path = Path(document.path)
        if not pdf_path.exists():
            return DocumentParseResult(
                success=False, error_message=f"File not found: {document.path}"
            )

        try:
            request = WorkerRequest(
                request_id=f"req_{document.document_id}_docling_ocr",
                parser_id=self.parser_id,
                input_path=str(pdf_path),
                document_id=document.document_id,
                source_sha256=document.sha256,
                page_count=document.page_count,
                options=self.spec.config,
            )

            resp = self.worker_client.execute_worker(request)

            if not resp.success or not resp.document_ir_dict:
                return DocumentParseResult(
                    success=False,
                    error_message=resp.error_message or "Docling OCR worker failed",
                )

            doc_ir = dict_to_document_ir(resp.document_ir_dict, profile)
            return DocumentParseResult(success=True, document_ir=doc_ir)

        except Exception as e:
            return DocumentParseResult(
                success=False, error_message=f"Docling OCR parse error: {e}"
            )
