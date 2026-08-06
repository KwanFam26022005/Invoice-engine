"""Docling OCR parser adapter for scanned & image-only PDFs using EasyOCR (vi, en)."""

import time
from pathlib import Path
from typing import List

from document_engine.core.models import PDFProfileType
from document_engine.ir.models import (
    BlockIR,
    DocumentIR,
    DocumentParseResult,
    DocumentProfile,
    PageIR,
    ParseWarning,
    ParserProvenance,
    SourceDocument,
    generate_block_id,
    generate_page_id,
)
from document_engine.parsers.base import DocumentParser, ParserHealth, ParserSpec


class DoclingOCRParser(DocumentParser):
    def __init__(self):
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
        self._converter = None

    @property
    def spec(self) -> ParserSpec:
        return self._spec

    def healthcheck(self) -> ParserHealth:
        try:
            import docling  # noqa: F401
            import easyocr  # noqa: F401
            return ParserHealth(
                parser_id=self.parser_id, healthy=True, message="Docling & EasyOCR available"
            )
        except ImportError as e:
            return ParserHealth(
                parser_id=self.parser_id,
                healthy=False,
                message=f"Missing dependencies for Docling OCR: {e}",
                dependencies_available=False,
            )

    def supports(self, profile: DocumentProfile) -> bool:
        return profile.pdf_profile in (
            PDFProfileType.SCAN_PDF,
            PDFProfileType.MIXED_PDF,
            PDFProfileType.NATIVE_PDF,
        )

    def prepare(self) -> None:
        if self._converter is None:
            try:
                from docling.document_converter import DocumentConverter, PdfFormatOption
                from docling.datamodel.pipeline_options import EasyOcrOptions, PdfPipelineOptions

                ocr_options = EasyOcrOptions(lang=["vi", "en"])
                pipeline_options = PdfPipelineOptions()
                pipeline_options.do_ocr = True
                pipeline_options.ocr_options = ocr_options
                pipeline_options.do_table_structure = True

                self._converter = DocumentConverter(
                    format_options={
                        "pdf": PdfFormatOption(pipeline_options=pipeline_options)
                    }
                )
            except Exception:
                self._converter = None

    def parse(self, document: SourceDocument, profile: DocumentProfile) -> DocumentParseResult:
        health = self.healthcheck()
        if not health.healthy:
            return DocumentParseResult(
                success=False,
                error_message=f"Docling OCR unavailable: {health.message}",
            )

        start_time = time.time()
        pdf_path = Path(document.path)
        if not pdf_path.exists():
            return DocumentParseResult(
                success=False, error_message=f"File not found: {document.path}"
            )

        try:
            if self._converter is None:
                self.prepare()
            if self._converter is None:
                return DocumentParseResult(
                    success=False, error_message="Docling OCR converter initialization failed."
                )

            result = self._converter.convert(str(pdf_path))
            docling_doc = result.document
            markdown_text = docling_doc.export_to_markdown()

            pages: List[PageIR] = []
            warnings: List[ParseWarning] = []

            for page_idx in range(document.page_count):
                page_num = page_idx + 1
                page_id = generate_page_id(document.document_id, page_num)
                block = BlockIR(
                    block_id=generate_block_id(page_id, 0),
                    page_number=page_num,
                    text=f"OCR Page {page_num} content",
                )
                pages.append(
                    PageIR(
                        page_id=page_id,
                        page_number=page_num,
                        width=595.0,
                        height=842.0,
                        blocks=[block],
                        tables=[],
                        text_content=markdown_text,
                    )
                )

            elapsed = time.time() - start_time
            provenance = ParserProvenance(
                parser_id=self.parser_id,
                parser_version=self.spec.version,
                execution_time_seconds=elapsed,
                config=self.spec.config,
            )

            doc_ir = DocumentIR(
                document_id=document.document_id,
                source_document=document,
                profile=profile,
                provenance=provenance,
                pages=pages,
                full_text=markdown_text,
                warnings=warnings,
            )

            return DocumentParseResult(success=True, document_ir=doc_ir)

        except Exception as e:
            return DocumentParseResult(
                success=False, error_message=f"Docling OCR parse error: {e}"
            )
