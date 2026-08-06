"""Unit and integration tests for dataset preparation pipeline."""

from pathlib import Path
import tempfile
import zipfile

import fitz

from scripts.prepare_benchmark_dataset import (
    DatasetPreparer,
    is_merged_file,
    is_pdf_magic_bytes,
    is_safe_zip_path,
    natural_sort_key,
    sanitize_filename,
)


def test_natural_sort_key():
    files = ["file_1.pdf", "file_10.pdf", "file_2.pdf", "file_02.pdf"]
    sorted_files = sorted(files, key=natural_sort_key)
    assert sorted_files == ["file_1.pdf", "file_2.pdf", "file_02.pdf", "file_10.pdf"]


def test_sanitize_filename():
    assert sanitize_filename("hóa_đơn:vận_tải?.pdf") == "hóa_đơn_vận_tải_.pdf"
    assert sanitize_filename("  test  file.pdf  ") == "test_file.pdf"
    assert sanitize_filename("normal_file.pdf") == "normal_file.pdf"


def test_is_merged_file():
    assert is_merged_file("mau_hd_merged.pdf") is True
    assert is_merged_file("sample_MERGED.pdf") is True
    assert is_merged_file("01GTKT0_055.pdf") is False


def test_zip_slip_prevention():
    target_dir = Path("/tmp/target").resolve()
    safe_path = target_dir / "subfolder" / "file.pdf"
    unsafe_path = target_dir / ".." / ".." / "etc" / "passwd"

    assert is_safe_zip_path(target_dir, safe_path) is True
    assert is_safe_zip_path(target_dir, unsafe_path) is False


def test_pdf_magic_bytes(tmp_path):
    valid_pdf = tmp_path / "valid.pdf"
    valid_pdf.write_bytes(b"%PDF-1.4 header text")

    invalid_txt = tmp_path / "invalid.txt"
    invalid_txt.write_bytes(b"NOT A PDF FILE")

    assert is_pdf_magic_bytes(valid_pdf) is True
    assert is_pdf_magic_bytes(invalid_txt) is False


def create_dummy_pdf(path: Path) -> None:
    """Helper to create a small valid PDF using PyMuPDF."""
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((50, 50), "Sample PDF text for benchmark test")
    doc.save(str(path))
    doc.close()


def test_dataset_preparer_integration_pipeline():
    with tempfile.TemporaryDirectory() as tmp_dir:
        root = Path(tmp_dir)

        # Create dummy ZIP archives
        vat_zip_path = root / "mau_hd_gtgt_thue_tong_co_chiet_khau_pdf.zip"
        util_zip_path = root / "mau_hd_gtgt_dien_va_nuoc_pdf.zip"
        sale_zip_path = root / "mau_hd_ban_hang_va_bien_lai_pdf.zip"

        pdf1 = root / "temp_1.pdf"
        pdf2 = root / "temp_2.pdf"
        merged_pdf = root / "temp_merged.pdf"
        create_dummy_pdf(pdf1)
        create_dummy_pdf(pdf2)
        create_dummy_pdf(merged_pdf)

        # Pack vat_zip
        with zipfile.ZipFile(vat_zip_path, "w") as z:
            z.write(pdf1, arcname="01GTKT0_001.pdf")
            z.write(pdf2, arcname="01GTKT0_002.pdf")
            z.write(merged_pdf, arcname="mau_hd_gtgt_thue_tong_co_chiet_khau_merged.pdf")
            z.writestr("manifest.txt", "ignore text file")

        # Pack util_zip
        with zipfile.ZipFile(util_zip_path, "w") as z:
            z.write(pdf1, arcname="01GTKT0_010.pdf")

        # Pack sale_zip
        with zipfile.ZipFile(sale_zip_path, "w") as z:
            z.write(pdf2, arcname="01BLP0_001.pdf")

        preparer = DatasetPreparer(
            dataset_root=root,
            overwrite_derived=True,
            copy_mode="copy",
        )
        summary = preparer.run()

        assert summary["total_archives"] == 3
        assert summary["individual_pdf_count"] == 4
        assert summary["merged_reference_count"] == 1
        assert (root / "benchmark" / "manifests" / "documents.csv").exists()
        assert (root / "benchmark" / "manifests" / "documents.jsonl").exists()
        assert (root / "benchmark" / "splits" / "smoke_test.txt").exists()
        assert (root / "benchmark" / "splits" / "benchmark_full.txt").exists()
        assert (root / "preparation_logs" / "summary.json").exists()

        # Test idempotency (rerunning preparer)
        summary2 = preparer.run()
        assert summary2["individual_pdf_count"] == 4
        assert summary2["valid_benchmark_count"] == summary["valid_benchmark_count"]
