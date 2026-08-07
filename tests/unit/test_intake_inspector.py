"""Unit tests for PDF intake inspector and document profiling."""

from pathlib import Path
import fitz
import pytest

from document_engine.core.exceptions import IntakeError
from document_engine.core.models import PDFProfileType
from document_engine.intake.inspector import PDFInspector


def create_synthetic_native_pdf(path: Path) -> Path:
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    page.insert_text(
        (50, 50),
        "CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM\nĐộc lập - Tự do - Hạnh phúc\nHÓA ĐƠN GIÁ TRỊ GIA TĂNG\nNgày 15 tháng 08 năm 2026",
    )
    page.insert_text(
        (50, 150),
        "Tên đơn vị bán hàng: Công ty TNHH Vận Tải Quốc Tế\nMã số thuế: 0101234567\nTổng tiền thanh toán: 12.500.000 VNĐ",
    )
    doc.save(path)
    doc.close()
    return path


def create_synthetic_scan_pdf(path: Path) -> Path:
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    # Insert minimal text (scanned image page representation)
    page.insert_text((50, 50), "Footer 1")
    doc.save(path)
    doc.close()
    return path


def create_synthetic_mixed_pdf(path: Path) -> Path:
    doc = fitz.open()
    # Page 1: Native text
    page1 = doc.new_page(width=595, height=842)
    page1.insert_text((50, 50), "HOA DON GIA TRI GIA TANG\nMa so thue: 0101234567\n" * 5)

    # Page 2: Scanned text page
    page2 = doc.new_page(width=595, height=842)
    page2.insert_text((50, 50), "1")
    doc.save(path)
    doc.close()
    return path


def create_synthetic_invalid_pdf(path: Path) -> Path:
    with open(path, "wb") as f:
        f.write(b"THIS IS NOT A PDF FILE HEADER")
    return path


def test_inspect_native_pdf(tmp_path: Path):
    pdf_path = create_synthetic_native_pdf(tmp_path / "sample_native.pdf")
    inspector = PDFInspector()
    source_doc, profile = inspector.inspect(pdf_path)

    assert source_doc.document_id.startswith("doc_")
    assert source_doc.page_count == 1
    assert profile.pdf_profile == PDFProfileType.NATIVE_PDF
    assert profile.has_text_layer is True
    assert profile.requires_ocr is False
    assert profile.text_character_count > 50


def test_inspect_scan_pdf(tmp_path: Path):
    pdf_path = create_synthetic_scan_pdf(tmp_path / "sample_scan.pdf")
    inspector = PDFInspector()
    _source_doc, profile = inspector.inspect(pdf_path)

    assert profile.pdf_profile == PDFProfileType.SCAN_PDF
    assert profile.requires_ocr is True


def test_inspect_mixed_pdf(tmp_path: Path):
    pdf_path = create_synthetic_mixed_pdf(tmp_path / "sample_mixed.pdf")
    inspector = PDFInspector()
    source_doc, profile = inspector.inspect(pdf_path)

    assert source_doc.page_count == 2
    assert profile.pdf_profile in (PDFProfileType.MIXED_PDF, PDFProfileType.NATIVE_PDF)


def test_inspect_invalid_pdf_header(tmp_path: Path):
    pdf_path = create_synthetic_invalid_pdf(tmp_path / "corrupt.pdf")
    inspector = PDFInspector()
    _source_doc, profile = inspector.inspect(pdf_path)

    assert profile.pdf_profile == PDFProfileType.INVALID_PDF
    assert profile.has_text_layer is False
    assert len(profile.inspection_warnings) > 0


def test_inspect_nonexistent_file(tmp_path: Path):
    inspector = PDFInspector()
    with pytest.raises(IntakeError):
        inspector.inspect(tmp_path / "non_existent.pdf")
