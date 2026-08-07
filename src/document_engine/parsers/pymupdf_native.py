"""PyMuPDF native PDF parser (fast, non-OCR text & layout extraction)."""

import time
from pathlib import Path
from typing import List, Optional
import fitz

from document_engine.core.models import PDFProfileType
from document_engine.ir.models import (
    BlockIR,
    DocumentIR,
    DocumentParseResult,
    DocumentProfile,
    Geometry,
    PageIR,
    ParseWarning,
    ParserProvenance,
    SourceDocument,
    generate_block_id,
    generate_page_id,
)
from document_engine.parsers.base import DocumentParser, ParserHealth, ParserSpec


class PyMuPDFNativeParser(DocumentParser):
    def __init__(self, config: Optional[dict] = None):
        self._spec = ParserSpec(
            parser_id="pymupdf_native",
            name="PyMuPDF Native Text Parser",
            version="1.0.0",
            supported_profiles=[PDFProfileType.NATIVE_PDF, PDFProfileType.MIXED_PDF],
            requires_gpu=False,
            is_fallback=False,
            config=config or {},
        )

    @property
    def spec(self) -> ParserSpec:
        return self._spec

    def healthcheck(self) -> ParserHealth:
        try:
            _ = fitz.VersionBind
            return ParserHealth(
                parser_id=self.parser_id, healthy=True, message="PyMuPDF available"
            )
        except Exception as e:
            return ParserHealth(
                parser_id=self.parser_id, healthy=False, message=str(e), dependencies_available=False
            )

    def supports(self, profile: DocumentProfile) -> bool:
        return profile.pdf_profile in (PDFProfileType.NATIVE_PDF, PDFProfileType.MIXED_PDF)

    def parse(self, document: SourceDocument, profile: DocumentProfile) -> DocumentParseResult:
        start_time = time.time()
        pdf_path = Path(document.path)
        if not pdf_path.exists():
            return DocumentParseResult(
                success=False,
                error_message=f"File not found: {document.path}",
            )

        warnings: List[ParseWarning] = []
        pages: List[PageIR] = []
        full_text_parts: List[str] = []

        try:
            doc = fitz.open(pdf_path)
            for page_idx, page in enumerate(doc):
                page_num = page_idx + 1
                page_id = generate_page_id(document.document_id, page_num)
                rect = page.rect
                width = rect.width if rect else 0.0
                height = rect.height if rect else 0.0

                # Get structured text blocks
                text_page = page.get_text("blocks")
                page_blocks: List[BlockIR] = []
                page_text_parts: List[str] = []

                for block_idx, b in enumerate(text_page):
                    # b format: (x0, y0, x1, y1, "text", block_no, block_type)
                    if len(b) >= 5:
                        x0, y0, x1, y1 = float(b[0]), float(b[1]), float(b[2]), float(b[3])
                        text_content = str(b[4]).strip()
                        block_type_code = b[6] if len(b) >= 7 else 0
                        block_type = "text" if block_type_code == 0 else "image"

                        if not text_content and block_type == "text":
                            continue

                        block_id = generate_block_id(page_id, block_idx)
                        geom = Geometry(
                            bbox=[x0, y0, x1, y1],
                            page_width=width,
                            page_height=height,
                        )
                        page_blocks.append(
                            BlockIR(
                                block_id=block_id,
                                page_number=page_num,
                                block_type=block_type,
                                text=text_content,
                                reading_order=block_idx,
                                geometry=geom,
                            )
                        )
                        if text_content:
                            page_text_parts.append(text_content)

                page_text = "\n".join(page_text_parts)
                pages.append(
                    PageIR(
                        page_id=page_id,
                        page_number=page_num,
                        width=width,
                        height=height,
                        blocks=page_blocks,
                        tables=[],
                        text_content=page_text,
                    )
                )
                if page_text:
                    full_text_parts.append(page_text)

            doc.close()
            elapsed = time.time() - start_time
            full_text = "\n\n".join(full_text_parts)

            if not full_text and profile.pdf_profile == PDFProfileType.NATIVE_PDF:
                warnings.append(
                    ParseWarning(
                        code="EMPTY_NATIVE_TEXT",
                        message="PyMuPDF extracted no text from native PDF.",
                    )
                )

            provenance = ParserProvenance(
                parser_id=self.parser_id,
                parser_version=self.spec.version,
                execution_time_seconds=elapsed,
            )

            doc_ir = DocumentIR(
                document_id=document.document_id,
                source_document=document,
                profile=profile,
                provenance=provenance,
                pages=pages,
                full_text=full_text,
                warnings=warnings,
            )

            return DocumentParseResult(
                success=True,
                document_ir=doc_ir,
                warnings=warnings,
            )

        except Exception as e:
            return DocumentParseResult(
                success=False,
                error_message=f"PyMuPDF native parsing failed: {e}",
            )
