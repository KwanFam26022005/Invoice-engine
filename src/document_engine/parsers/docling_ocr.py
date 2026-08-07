"""Docling OCR parser adapter for scanned & image-only PDFs via isolated worker."""

import time
from pathlib import Path
from typing import List, Optional

from document_engine.core.models import PDFProfileType
from document_engine.ir.models import (
    DocumentParseResult,
    DocumentProfile,
    SourceDocument,
)
from document_engine.parsers.base import DocumentParser, ParserHealth, ParserSpec
from document_engine.parsers.docling_native import dict_to_document_ir
from document_engine.runtime import WorkerClient, WorkerRequest, resolve_worker_python


class DoclingOCRParser(DocumentParser):
    def __init__(self, worker_client: Optional[WorkerClient] = None):
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
            config={
                "do_ocr": True,
                "ocr_engine": "easyocr",
                "ocr_languages": ["vi", "en"],
                "do_table_structure": True,
            },
        )
        self.worker_client = worker_client or WorkerClient()

    @property
    def spec(self) -> ParserSpec:
        return self._spec

    def healthcheck(self) -> ParserHealth:
        import importlib.util

        has_docling_in_base = (
            importlib.util.find_spec("docling") is not None
            and importlib.util.find_spec("easyocr") is not None
        )
        python_bin = resolve_worker_python(self.parser_id)
        is_isolated = python_bin != Path(python_bin).name

        if has_docling_in_base or is_isolated:
            return ParserHealth(
                parser_id=self.parser_id, healthy=True, message="Docling OCR available"
            )
        return ParserHealth(
            parser_id=self.parser_id,
            healthy=False,
            message="Missing dependencies for Docling OCR in base and worker environments",
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
