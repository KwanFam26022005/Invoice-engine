"""Tests for deterministic smoke split loading."""

from __future__ import annotations

import csv
import hashlib
from pathlib import Path

import pytest

from document_benchmark.smoke.dataset import SmokeDatasetError, load_smoke_dataset


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _build_dataset(root: Path, count: int = 2) -> None:
    manifest = root / "benchmark" / "manifests" / "documents.csv"
    split = root / "benchmark" / "splits" / "smoke_test.txt"
    documents_dir = root / "benchmark" / "documents" / "sample"
    documents_dir.mkdir(parents=True)
    manifest.parent.mkdir(parents=True)
    split.parent.mkdir(parents=True)

    fieldnames = [
        "document_id",
        "dataset_category",
        "document_family",
        "source_group",
        "benchmark_filename",
        "benchmark_path",
        "sha256",
        "page_count",
        "has_text_layer",
        "text_character_count",
        "is_image_only_pdf",
        "is_merged",
        "include_in_benchmark",
        "quality_status",
        "ground_truth_level",
    ]
    rows = []
    ids = []
    for index in range(1, count + 1):
        document_id = f"DOC-{index:04d}"
        filename = f"sample_{index:04d}.pdf"
        path = documents_dir / filename
        path.write_bytes(b"%PDF-1.4\nsynthetic smoke fixture\n%%EOF\n")
        ids.append(document_id)
        rows.append(
            {
                "document_id": document_id,
                "dataset_category": "sample",
                "document_family": "INVOICE",
                "source_group": "TEST",
                "benchmark_filename": filename,
                "benchmark_path": f"benchmark/documents/sample/{filename}",
                "sha256": _sha(path),
                "page_count": "1",
                "has_text_layer": "False",
                "text_character_count": "0",
                "is_image_only_pdf": "True",
                "is_merged": "False",
                "include_in_benchmark": "True",
                "quality_status": "VALID",
                "ground_truth_level": "0",
            }
        )
    with manifest.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    split.write_text("\n".join(reversed(ids)) + "\n", encoding="utf-8")


def test_load_smoke_dataset_preserves_split_order_and_fingerprint(tmp_path: Path) -> None:
    _build_dataset(tmp_path)
    first = load_smoke_dataset(tmp_path, expected_count=2)
    second = load_smoke_dataset(tmp_path, expected_count=2)

    assert first.document_ids == ["DOC-0002", "DOC-0001"]
    assert first.fingerprint == second.fingerprint
    assert all(document.metadata["input_profile"] == "scan_ocr" for document in first.documents)
    assert all(document.metadata["ground_truth_level"] == 0 for document in first.documents)


def test_load_smoke_dataset_rejects_hash_mismatch(tmp_path: Path) -> None:
    _build_dataset(tmp_path, count=1)
    pdf = tmp_path / "benchmark" / "documents" / "sample" / "sample_0001.pdf"
    pdf.write_bytes(pdf.read_bytes() + b"changed")

    with pytest.raises(SmokeDatasetError, match="SHA-256 mismatch"):
        load_smoke_dataset(tmp_path, expected_count=1)


def test_load_smoke_dataset_rejects_path_escape(tmp_path: Path) -> None:
    _build_dataset(tmp_path, count=1)
    manifest = tmp_path / "benchmark" / "manifests" / "documents.csv"
    content = manifest.read_text(encoding="utf-8")
    manifest.write_text(
        content.replace(
            "benchmark/documents/sample/sample_0001.pdf",
            "../outside.pdf",
        ),
        encoding="utf-8",
    )

    with pytest.raises(SmokeDatasetError, match="escapes dataset root"):
        load_smoke_dataset(tmp_path, expected_count=1)
