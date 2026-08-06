"""Load a deterministic benchmark split from the sanitized dataset manifest."""

from __future__ import annotations

import csv
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path

from document_benchmark.core.contracts import DocumentInput

_TRUE_VALUES = {"1", "true", "yes", "y"}
_FALSE_VALUES = {"0", "false", "no", "n", ""}


class SmokeDatasetError(ValueError):
    """Raised when the smoke split or its local document files are inconsistent."""


@dataclass(frozen=True)
class SmokeDataset:
    """Resolved smoke split and its reproducibility fingerprint."""

    dataset_root: Path
    manifest_path: Path
    split_path: Path
    documents: list[DocumentInput]
    fingerprint: str

    @property
    def document_ids(self) -> list[str]:
        return [document.document_id for document in self.documents]


def _parse_bool(value: str | bool | None, *, field_name: str) -> bool:
    if isinstance(value, bool):
        return value
    normalized = str(value or "").strip().casefold()
    if normalized in _TRUE_VALUES:
        return True
    if normalized in _FALSE_VALUES:
        return False
    raise SmokeDatasetError(f"Invalid boolean value for {field_name}: {value!r}")


def _safe_dataset_path(dataset_root: Path, relative_value: str) -> Path:
    if not relative_value:
        raise SmokeDatasetError("Manifest benchmark_path is empty")
    root = dataset_root.resolve()
    candidate = (root / Path(relative_value)).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise SmokeDatasetError(
            f"Manifest path escapes dataset root: {relative_value}"
        ) from exc
    return candidate


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _input_profile(row: dict[str, str]) -> str | None:
    has_text = _parse_bool(row.get("has_text_layer"), field_name="has_text_layer")
    is_image_only = _parse_bool(
        row.get("is_image_only_pdf"), field_name="is_image_only_pdf"
    )
    if has_text:
        return "native_pdf"
    if is_image_only:
        return "scan_ocr"
    return None


def _fingerprint_payload(documents: list[DocumentInput]) -> str:
    payload = [
        {
            "document_id": document.document_id,
            "sha256": document.sha256,
            "filename": document.filename,
            "page_count": document.page_count,
            "input_profile": document.metadata.get("input_profile"),
        }
        for document in documents
    ]
    canonical = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def load_smoke_dataset(
    dataset_root: str | Path,
    *,
    split_path: str | Path = "benchmark/splits/smoke_test.txt",
    manifest_path: str | Path = "benchmark/manifests/documents.csv",
    verify_hashes: bool = True,
    expected_count: int | None = 10,
    expected_profile: str | None = "scan_ocr",
) -> SmokeDataset:
    """Resolve one ordered split into validated ``DocumentInput`` records.

    The loader never performs OCR and never rewrites dataset files. The order in
    the split file is preserved so all engines process the same documents in the
    same order.
    """

    root = Path(dataset_root).resolve()
    resolved_manifest = _safe_dataset_path(root, str(manifest_path))
    resolved_split = _safe_dataset_path(root, str(split_path))

    if not resolved_manifest.is_file():
        raise SmokeDatasetError(f"Manifest not found: {resolved_manifest}")
    if not resolved_split.is_file():
        raise SmokeDatasetError(f"Split not found: {resolved_split}")

    document_ids = [
        line.strip()
        for line in resolved_split.read_text(encoding="utf-8-sig").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    if not document_ids:
        raise SmokeDatasetError(f"Split is empty: {resolved_split}")
    if len(document_ids) != len(set(document_ids)):
        raise SmokeDatasetError("Split contains duplicate document IDs")
    if expected_count is not None and len(document_ids) != expected_count:
        raise SmokeDatasetError(
            f"Expected {expected_count} documents, found {len(document_ids)}"
        )

    with resolved_manifest.open(encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    rows_by_id = {row.get("document_id", "").strip(): row for row in rows}
    if len(rows_by_id) != len(rows):
        raise SmokeDatasetError("Manifest contains duplicate document IDs")

    documents: list[DocumentInput] = []
    for document_id in document_ids:
        row = rows_by_id.get(document_id)
        if row is None:
            raise SmokeDatasetError(f"Split document missing from manifest: {document_id}")
        if not _parse_bool(
            row.get("include_in_benchmark"), field_name="include_in_benchmark"
        ):
            raise SmokeDatasetError(f"Document is excluded from benchmark: {document_id}")
        if _parse_bool(row.get("is_merged"), field_name="is_merged"):
            raise SmokeDatasetError(f"Merged reference cannot enter smoke split: {document_id}")
        if row.get("quality_status", "").strip().upper() != "VALID":
            raise SmokeDatasetError(
                f"Document is not VALID: {document_id} ({row.get('quality_status')})"
            )

        pdf_path = _safe_dataset_path(root, row.get("benchmark_path", ""))
        if not pdf_path.is_file():
            raise SmokeDatasetError(f"Benchmark PDF not found: {pdf_path}")
        with pdf_path.open("rb") as stream:
            if stream.read(4) != b"%PDF":
                raise SmokeDatasetError(f"Invalid PDF magic bytes: {pdf_path}")

        expected_sha = row.get("sha256", "").strip().lower()
        if not expected_sha:
            raise SmokeDatasetError(f"Missing SHA-256 for {document_id}")
        if verify_hashes:
            actual_sha = _sha256(pdf_path)
            if actual_sha != expected_sha:
                raise SmokeDatasetError(
                    f"SHA-256 mismatch for {document_id}: expected {expected_sha}, got {actual_sha}"
                )

        profile = _input_profile(row)
        if expected_profile is not None and profile != expected_profile:
            raise SmokeDatasetError(
                f"Document {document_id} has profile {profile!r}, expected {expected_profile!r}"
            )

        documents.append(
            DocumentInput(
                document_id=document_id,
                path=str(pdf_path),
                filename=row.get("benchmark_filename", "").strip() or pdf_path.name,
                sha256=expected_sha,
                page_count=int(row.get("page_count") or 1),
                metadata={
                    "dataset_category": row.get("dataset_category", ""),
                    "document_family": row.get("document_family", ""),
                    "source_group": row.get("source_group", ""),
                    "ground_truth_level": int(row.get("ground_truth_level") or 0),
                    "has_text_layer": _parse_bool(
                        row.get("has_text_layer"), field_name="has_text_layer"
                    ),
                    "is_image_only_pdf": _parse_bool(
                        row.get("is_image_only_pdf"),
                        field_name="is_image_only_pdf",
                    ),
                    "text_character_count": int(row.get("text_character_count") or 0),
                    "input_profile": profile,
                    "benchmark_path": row.get("benchmark_path", ""),
                },
            )
        )

    return SmokeDataset(
        dataset_root=root,
        manifest_path=resolved_manifest,
        split_path=resolved_split,
        documents=documents,
        fingerprint=_fingerprint_payload(documents),
    )
