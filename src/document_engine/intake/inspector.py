"""PDF Inspection module using PyMuPDF (fitz) for fast, non-OCR document profiling."""

import hashlib
from pathlib import Path
from typing import List, Tuple
import fitz  # PyMuPDF

from document_engine.core.exceptions import IntakeError
from document_engine.core.models import PDFProfileType
from document_engine.ir.models import (
    DocumentProfile,
    SourceDocument,
    generate_document_id,
)


class PDFInspector:
    def __init__(
        self,
        min_native_chars_per_page: int = 40,
        full_page_img_threshold: float = 0.75,
        scan_max_text_chars_per_page: int = 15,
    ):
        self.min_native_chars_per_page = min_native_chars_per_page
        self.full_page_img_threshold = full_page_img_threshold
        self.scan_max_text_chars_per_page = scan_max_text_chars_per_page

    def inspect(self, pdf_path: Path) -> Tuple[SourceDocument, DocumentProfile]:
        pdf_path = Path(pdf_path).resolve()
        if not pdf_path.exists() or not pdf_path.is_file():
            raise IntakeError(f"File not found: {pdf_path}")

        # Magic bytes check (%PDF-)
        with open(pdf_path, "rb") as f:
            header = f.read(5)
            f.seek(0)
            sha256 = hashlib.sha256(f.read()).hexdigest()

        if not header.startswith(b"%PDF"):
            profile = DocumentProfile(
                pdf_profile=PDFProfileType.INVALID_PDF,
                has_text_layer=False,
                inspection_warnings=["Invalid PDF magic bytes header."],
            )
            doc_id = generate_document_id(sha256)
            source_doc = SourceDocument(
                document_id=doc_id,
                filename=pdf_path.name,
                path=str(pdf_path),
                mime_type="application/pdf",
                sha256=sha256,
                page_count=0,
            )
            return source_doc, profile

        try:
            doc = fitz.open(pdf_path)
        except Exception as e:
            profile = DocumentProfile(
                pdf_profile=PDFProfileType.INVALID_PDF,
                has_text_layer=False,
                inspection_warnings=[f"Failed to open PDF with PyMuPDF: {e}"],
            )
            doc_id = generate_document_id(sha256)
            source_doc = SourceDocument(
                document_id=doc_id,
                filename=pdf_path.name,
                path=str(pdf_path),
                mime_type="application/pdf",
                sha256=sha256,
                page_count=0,
            )
            return source_doc, profile

        page_count = len(doc)
        if page_count == 0:
            doc.close()
            profile = DocumentProfile(
                pdf_profile=PDFProfileType.INVALID_PDF,
                has_text_layer=False,
                inspection_warnings=["PDF contains zero pages."],
            )
            doc_id = generate_document_id(sha256)
            source_doc = SourceDocument(
                document_id=doc_id,
                filename=pdf_path.name,
                path=str(pdf_path),
                mime_type="application/pdf",
                sha256=sha256,
                page_count=0,
            )
            return source_doc, profile

        total_text_chars = 0
        total_images = 0
        full_page_images = 0
        native_pages = 0
        scan_pages = 0
        warnings: List[str] = []

        for page_idx in range(page_count):
            page = doc[page_idx]
            page_rect = page.rect
            page_area = page_rect.width * page_rect.height if page_rect else 1.0

            text = page.get_text("text").strip()
            text_len = len(text)
            total_text_chars += text_len

            images = page.get_images(full=True)
            image_count = len(images)
            total_images += image_count

            # Check for full-page images
            is_full_page_img = False
            for img_info in images:
                xref = img_info[0]
                try:
                    rects = page.get_image_rects(xref)
                    for r in rects:
                        img_area = r.width * r.height
                        if page_area > 0 and (img_area / page_area) >= self.full_page_img_threshold:
                            is_full_page_img = True
                            break
                except Exception:
                    pass
                if is_full_page_img:
                    break

            if is_full_page_img:
                full_page_images += 1

            if text_len >= self.min_native_chars_per_page and not is_full_page_img:
                native_pages += 1
            elif text_len <= self.scan_max_text_chars_per_page or is_full_page_img:
                scan_pages += 1
            else:
                # Borderline text
                if text_len < self.min_native_chars_per_page:
                    warnings.append(
                        f"Page {page_idx + 1} has low text count ({text_len} chars), likely header/watermark."
                    )
                scan_pages += 1

        doc.close()

        has_text_layer = total_text_chars > (self.min_native_chars_per_page * page_count * 0.5)
        text_density = total_text_chars / page_count if page_count > 0 else 0.0
        full_page_ratio = full_page_images / page_count if page_count > 0 else 0.0

        if native_pages == page_count:
            pdf_profile = PDFProfileType.NATIVE_PDF
            requires_ocr = False
        elif scan_pages == page_count or (total_text_chars < self.scan_max_text_chars_per_page * page_count):
            pdf_profile = PDFProfileType.SCAN_PDF
            requires_ocr = True
        else:
            pdf_profile = PDFProfileType.MIXED_PDF
            requires_ocr = True

        doc_id = generate_document_id(sha256)
        source_doc = SourceDocument(
            document_id=doc_id,
            filename=pdf_path.name,
            path=str(pdf_path),
            mime_type="application/pdf",
            sha256=sha256,
            page_count=page_count,
            source_metadata={
                "native_pages": native_pages,
                "scan_pages": scan_pages,
            },
        )

        profile = DocumentProfile(
            pdf_profile=pdf_profile,
            has_text_layer=has_text_layer,
            text_character_count=total_text_chars,
            text_density=text_density,
            image_count=total_images,
            full_page_image_ratio=full_page_ratio,
            requires_ocr=requires_ocr,
            inspection_warnings=warnings,
        )

        return source_doc, profile
