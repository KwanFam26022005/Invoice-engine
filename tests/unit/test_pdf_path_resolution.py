"""Unit tests for PDF path resolution and path containment security."""

from pathlib import Path

from document_benchmark.ui.comparison_loader import resolve_pdf_path
from document_benchmark.ui.pdf_rendering import get_pdf_base64_data_uri, render_pdf_page_to_png_bytes


def test_resolve_pdf_path_valid(tmp_path: Path) -> None:
    dataset_root = tmp_path / "datasets"
    pdf_dir = dataset_root / "benchmark" / "documents"
    pdf_dir.mkdir(parents=True)

    dummy_pdf = pdf_dir / "sample.pdf"
    dummy_pdf.write_bytes(b"%PDF-1.4 sample pdf content")

    resolved, is_avail, err = resolve_pdf_path(dataset_root, "benchmark/documents/sample.pdf")
    assert is_avail is True
    assert err is None
    assert resolved == dummy_pdf.resolve()


def test_resolve_pdf_path_traversal_blocked(tmp_path: Path) -> None:
    dataset_root = tmp_path / "datasets"
    dataset_root.mkdir()

    outside_file = tmp_path / "secret.pdf"
    outside_file.write_bytes(b"%PDF-1.4 secret content")

    _resolved, is_avail, err = resolve_pdf_path(dataset_root, "../secret.pdf")
    assert is_avail is False
    assert err is not None
    assert "containment violation" in err.lower() or "outside base directory" in err.lower()


def test_get_pdf_base64_data_uri_invalid_magic(tmp_path: Path) -> None:
    fake_file = tmp_path / "fake.pdf"
    fake_file.write_bytes(b"NOT A PDF FILE DATA")

    data_uri = get_pdf_base64_data_uri(fake_file)
    assert data_uri is None


def test_render_pdf_page_missing(tmp_path: Path) -> None:
    non_existent = tmp_path / "missing.pdf"
    res = render_pdf_page_to_png_bytes(non_existent)
    assert res is None
