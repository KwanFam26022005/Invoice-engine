"""Unit and integration tests for dataset preparation."""

from __future__ import annotations

import csv
import json
from pathlib import Path
import tempfile
import time
import zipfile

import fitz
import pytest

from scripts.prepare_benchmark_dataset import (
    ARCHIVE_MAPPINGS,
    DatasetPreparer,
    compute_sha256,
    extract_zip_safely,
    is_merged_file,
    is_pdf_magic_bytes,
    is_safe_zip_path,
    natural_sort_key,
    sanitize_filename,
)


def create_dummy_pdf(path: Path, text: str = "Sample PDF text for benchmark test") -> None:
    with fitz.open() as document:
        page = document.new_page()
        page.insert_text((50, 50), text)
        document.save(path)


def build_fixture_dataset(root: Path, *, include_duplicate: bool = False) -> None:
    pdf1 = root / "temp_1.pdf"
    pdf2 = root / "temp_2.pdf"
    merged = root / "temp_merged.pdf"
    create_dummy_pdf(pdf1, "A" * 80)
    create_dummy_pdf(pdf2, "B" * 80)
    create_dummy_pdf(merged, "Merged" * 20)

    archive_names = list(ARCHIVE_MAPPINGS)
    with zipfile.ZipFile(root / archive_names[0], "w") as archive:
        archive.write(pdf1, arcname="01GTKT0_001.pdf")
        archive.write(pdf2, arcname="01GTKT0_002.pdf")
        archive.write(merged, arcname="source_merged.pdf")
        archive.writestr("manifest.txt", "not a PDF")
    with zipfile.ZipFile(root / archive_names[1], "w") as archive:
        archive.write(pdf1 if include_duplicate else pdf2, arcname="01GTKT0_010.pdf")
    with zipfile.ZipFile(root / archive_names[2], "w") as archive:
        archive.write(pdf2, arcname="receipt_001.pdf")


def test_natural_sort_key() -> None:
    files = ["file_1.pdf", "file_10.pdf", "file_2.pdf", "file_02.pdf"]
    assert sorted(files, key=natural_sort_key) == [
        "file_1.pdf",
        "file_2.pdf",
        "file_02.pdf",
        "file_10.pdf",
    ]


def test_sanitize_filename() -> None:
    assert sanitize_filename("hóa_đơn:vận_tải?.pdf") == "hóa_đơn_vận_tải_.pdf"
    assert sanitize_filename("  test  file.pdf  ") == "test_file.pdf"
    assert sanitize_filename("normal_file.pdf") == "normal_file.pdf"


def test_is_merged_file() -> None:
    assert is_merged_file("mau_hd_merged.pdf")
    assert is_merged_file("sample_MERGED.pdf")
    assert not is_merged_file("01GTKT0_055.pdf")


def test_zip_slip_and_prefix_bypass_prevention(tmp_path: Path) -> None:
    target = tmp_path / "target"
    assert is_safe_zip_path(target, target / "subfolder" / "file.pdf")
    assert not is_safe_zip_path(target, target / ".." / "outside" / "file.pdf")
    assert not is_safe_zip_path(target, tmp_path / "target_evil" / "file.pdf")


def test_extract_zip_safely_blocks_traversal(tmp_path: Path) -> None:
    archive_path = tmp_path / "unsafe.zip"
    output = tmp_path / "output"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("safe/file.txt", "safe")
        archive.writestr("../escape.txt", "unsafe")

    extracted = extract_zip_safely(archive_path, output)
    assert [path.relative_to(output).as_posix() for path in extracted] == ["safe/file.txt"]
    assert not (tmp_path / "escape.txt").exists()


def test_pdf_magic_and_sha256(tmp_path: Path) -> None:
    valid_pdf = tmp_path / "valid.pdf"
    create_dummy_pdf(valid_pdf)
    invalid = tmp_path / "invalid.txt"
    invalid.write_bytes(b"NOT PDF")

    assert is_pdf_magic_bytes(valid_pdf)
    assert not is_pdf_magic_bytes(invalid)
    assert compute_sha256(valid_pdf) == compute_sha256(valid_pdf)


def test_smoke_size_is_honored(tmp_path: Path) -> None:
    build_fixture_dataset(tmp_path)
    summary = DatasetPreparer(tmp_path, overwrite_derived=True, smoke_size=2).run()
    smoke = (tmp_path / "benchmark" / "splits" / "smoke_test.txt").read_text(
        encoding="utf-8"
    ).splitlines()
    assert summary["smoke_test_count"] == 2
    assert len(smoke) == 2


def test_duplicate_report_contains_primary_path(tmp_path: Path) -> None:
    build_fixture_dataset(tmp_path, include_duplicate=True)
    summary = DatasetPreparer(tmp_path, overwrite_derived=True).run()
    assert summary["duplicate_count"] >= 1

    with (tmp_path / "benchmark" / "manifests" / "duplicates.csv").open(
        encoding="utf-8", newline=""
    ) as stream:
        rows = list(csv.DictReader(stream))
    assert rows
    assert rows[0]["primary_document_id"].startswith(("VATD-", "UTIL-", "SALE-"))
    assert rows[0]["primary_path"].startswith("benchmark/documents/")
    assert rows[0]["primary_path"].endswith(".pdf")


def test_verify_only_is_read_only(tmp_path: Path) -> None:
    build_fixture_dataset(tmp_path)
    DatasetPreparer(tmp_path, overwrite_derived=True).run()

    tracked = [
        tmp_path / "benchmark" / "manifests" / "documents.csv",
        tmp_path / "benchmark" / "manifests" / "documents.jsonl",
        tmp_path / "preparation_logs" / "summary.json",
    ]
    before = {path: (path.stat().st_mtime_ns, path.read_bytes()) for path in tracked}
    time.sleep(0.01)

    result = DatasetPreparer(tmp_path, verify_only=True).run()
    after = {path: (path.stat().st_mtime_ns, path.read_bytes()) for path in tracked}

    assert result["verification_status"] == "PASSED"
    assert before == after


def test_verify_only_detects_hash_mismatch(tmp_path: Path) -> None:
    build_fixture_dataset(tmp_path)
    DatasetPreparer(tmp_path, overwrite_derived=True).run()
    manifest = tmp_path / "benchmark" / "manifests" / "documents.csv"
    rows = list(csv.DictReader(manifest.open(encoding="utf-8", newline="")))
    benchmark_file = next(
        tmp_path / row["benchmark_path"] for row in rows if row["include_in_benchmark"] == "True"
    )
    benchmark_file.write_bytes(benchmark_file.read_bytes() + b"tamper")

    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        DatasetPreparer(tmp_path, verify_only=True).run()


def test_overwrite_derived_removes_stale_artifacts(tmp_path: Path) -> None:
    build_fixture_dataset(tmp_path)
    preparer = DatasetPreparer(tmp_path, overwrite_derived=True)
    preparer.run()
    stale = tmp_path / "benchmark" / "documents" / "stale.pdf"
    stale.write_bytes(b"stale")

    preparer.run()
    assert not stale.exists()


def test_dataset_preparer_integration_pipeline(tmp_path: Path) -> None:
    build_fixture_dataset(tmp_path)
    preparer = DatasetPreparer(tmp_path, overwrite_derived=True, copy_mode="copy")
    summary = preparer.run()

    assert summary["total_archives"] == 3
    assert summary["individual_pdf_count"] == 4
    assert summary["merged_reference_count"] == 1
    assert (tmp_path / "benchmark" / "manifests" / "documents.csv").exists()
    assert (tmp_path / "benchmark" / "manifests" / "documents.jsonl").exists()
    assert (tmp_path / "benchmark" / "splits" / "smoke_test.txt").exists()
    assert (tmp_path / "benchmark" / "splits" / "benchmark_full.txt").exists()
    assert (tmp_path / "preparation_logs" / "summary.json").exists()

    first_manifest = (tmp_path / "benchmark" / "manifests" / "documents.jsonl").read_text(
        encoding="utf-8"
    )
    second_summary = preparer.run()
    second_manifest = (tmp_path / "benchmark" / "manifests" / "documents.jsonl").read_text(
        encoding="utf-8"
    )
    assert second_summary == summary
    assert json.loads(first_manifest.splitlines()[0]) == json.loads(second_manifest.splitlines()[0])


def test_negative_smoke_size_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="non-negative"):
        DatasetPreparer(tmp_path, smoke_size=-1)
