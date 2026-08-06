"""Tests for CLI PDF input-profile inspection."""

from pathlib import Path

import fitz

from document_benchmark.cli import inspect_pdf_profile


def test_inspect_pdf_profile_detects_native_text(tmp_path: Path) -> None:
    pdf_path = tmp_path / "native.pdf"
    with fitz.open() as document:
        page = document.new_page()
        page.insert_text((50, 50), "Vietnamese invoice text " * 8)
        document.save(pdf_path)

    page_count, metadata = inspect_pdf_profile(pdf_path)
    assert page_count == 1
    assert metadata["has_text_layer"] is True
    assert metadata["is_image_only_pdf"] is False
    assert metadata["input_profile"] == "native_pdf"


def test_inspect_pdf_profile_detects_image_only_pdf(tmp_path: Path) -> None:
    pdf_path = tmp_path / "scan.pdf"
    with fitz.open() as document:
        document.new_page()
        document.save(pdf_path)

    page_count, metadata = inspect_pdf_profile(pdf_path)
    assert page_count == 1
    assert metadata["has_text_layer"] is False
    assert metadata["is_image_only_pdf"] is True
    assert metadata["input_profile"] == "scan_ocr"
