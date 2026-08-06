"""Prepare and verify the local PDF corpus used by the benchmark.

Preparation is intentionally deterministic and local-only. ``--verify-only`` is
strictly read-only: it never creates directories, extracts archives, copies
files, or rewrites manifests.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import logging
import os
from pathlib import Path
import re
import shutil
import sys
from typing import Any
import zipfile

import fitz

logger = logging.getLogger("dataset_preparation")

ARCHIVE_MAPPINGS: dict[str, dict[str, str]] = {
    "mau_hd_gtgt_thue_tong_co_chiet_khau_pdf.zip": {
        "category": "vat_discount",
        "document_family": "INVOICE",
        "source_group": "VAT_DISCOUNT",
        "prefix": "VATD",
    },
    "mau_hd_gtgt_dien_va_nuoc_pdf.zip": {
        "category": "utilities",
        "document_family": "INVOICE",
        "source_group": "UTILITIES",
        "prefix": "UTIL",
    },
    "mau_hd_ban_hang_va_bien_lai_pdf.zip": {
        "category": "sales_receipts",
        "document_family": "INVOICE_OR_RECEIPT",
        "source_group": "SALES_RECEIPTS",
        "prefix": "SALE",
    },
}

MANIFEST_FIELDS = [
    "document_id",
    "dataset_category",
    "document_family",
    "source_group",
    "source_archive",
    "original_filename",
    "benchmark_filename",
    "raw_path",
    "benchmark_path",
    "sha256",
    "file_size_bytes",
    "page_count",
    "width_points",
    "height_points",
    "has_text_layer",
    "text_character_count",
    "is_image_only_pdf",
    "is_merged",
    "include_in_benchmark",
    "duplicate_of",
    "quality_status",
    "ground_truth_level",
    "notes",
]


def natural_sort_key(value: str) -> list[Any]:
    """Return a case-insensitive natural-sort key."""
    return [int(part) if part.isdigit() else part.lower() for part in re.split(r"(\d+)", value)]


def sanitize_filename(filename: str) -> str:
    """Return a Windows-safe basename while preserving Unicode letters."""
    name = Path(filename).name
    sanitized = re.sub(r'[\\/*?:"<>|\s]', "_", name)
    sanitized = re.sub(r"_+", "_", sanitized).strip("_")
    return sanitized or "document.pdf"


def compute_sha256(file_path: Path) -> str:
    digest = hashlib.sha256()
    with file_path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def is_pdf_magic_bytes(file_path: Path) -> bool:
    try:
        with file_path.open("rb") as stream:
            return stream.read(4) == b"%PDF"
    except OSError:
        return False


def is_safe_zip_path(target_dir: Path, extracted_path: Path) -> bool:
    """Check path containment without vulnerable string-prefix matching."""
    try:
        extracted_path.resolve().relative_to(target_dir.resolve())
        return True
    except (OSError, ValueError):
        return False


def extract_zip_safely(zip_path: Path, extract_dir: Path) -> list[Path]:
    """Extract regular ZIP members while blocking traversal and symlinks."""
    extracted: list[Path] = []
    with zipfile.ZipFile(zip_path) as archive:
        bad_member = archive.testzip()
        if bad_member:
            raise zipfile.BadZipFile(f"CRC check failed for member: {bad_member}")

        for member in archive.infolist():
            if member.is_dir():
                continue
            # Unix symlink bit in external attributes.
            if (member.external_attr >> 16) & 0o170000 == 0o120000:
                logger.warning("Blocked ZIP symlink: %s", member.filename)
                continue

            target_path = extract_dir / member.filename
            if not is_safe_zip_path(extract_dir, target_path):
                logger.warning("Blocked ZIP traversal member: %s", member.filename)
                continue

            target_path.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(member) as source, target_path.open("wb") as destination:
                shutil.copyfileobj(source, destination)
            extracted.append(target_path)
    return extracted


def inspect_pdf(file_path: Path) -> dict[str, Any]:
    result: dict[str, Any] = {
        "page_count": 0,
        "width_points": 0.0,
        "height_points": 0.0,
        "has_text_layer": False,
        "text_character_count": 0,
        "is_image_only_pdf": True,
        "is_valid_pdf": False,
        "error": None,
    }
    if not is_pdf_magic_bytes(file_path):
        result["error"] = "Invalid PDF magic bytes"
        return result

    try:
        with fitz.open(file_path) as document:
            result["page_count"] = len(document)
            if not document:
                result["error"] = "Empty PDF"
                return result
            rect = document[0].rect
            result["width_points"] = round(rect.width, 2)
            result["height_points"] = round(rect.height, 2)
            text_count = sum(len(page.get_text().strip()) for page in document)
            result["text_character_count"] = text_count
            result["has_text_layer"] = text_count >= 50
            result["is_image_only_pdf"] = text_count < 50
            result["is_valid_pdf"] = True
    except Exception as exc:
        result["error"] = str(exc)
    return result


def is_merged_file(filename: str) -> bool:
    return "merged" in filename.casefold()


def read_split(path: Path) -> list[str]:
    if not path.exists():
        return []
    return [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def parse_bool(value: Any) -> bool:
    return str(value).strip().casefold() in {"1", "true", "yes"}


class DatasetPreparer:
    """Prepare derived dataset artifacts or verify an existing corpus."""

    def __init__(
        self,
        dataset_root: Path,
        overwrite_derived: bool = False,
        dry_run: bool = False,
        verify_only: bool = False,
        smoke_size: int = 10,
        copy_mode: str = "copy",
    ) -> None:
        if smoke_size < 0:
            raise ValueError("smoke_size must be non-negative")
        self.dataset_root = dataset_root.resolve()
        self.overwrite = overwrite_derived
        self.dry_run = dry_run
        self.verify_only = verify_only
        self.smoke_size = smoke_size
        self.copy_mode = copy_mode

        self.archives_dir = self.dataset_root / "archives"
        self.staging_dir = self.dataset_root / "staging"
        self.raw_dir = self.dataset_root / "raw"
        self.ref_merged_dir = self.dataset_root / "reference_merged"
        self.benchmark_dir = self.dataset_root / "benchmark"
        self.documents_dir = self.benchmark_dir / "documents"
        self.ground_truth_dir = self.benchmark_dir / "ground_truth"
        self.manifests_dir = self.benchmark_dir / "manifests"
        self.splits_dir = self.benchmark_dir / "splits"
        self.logs_dir = self.dataset_root / "preparation_logs"

    def run(self) -> dict[str, Any]:
        if self.verify_only:
            return self.verify_existing_dataset()

        logger.info("Starting dataset preparation at %s", self.dataset_root)
        self._prepare_output_directories()
        archives = self._collect_archives()
        if not archives:
            raise FileNotFoundError("No configured ZIP archives were found")

        records: list[dict[str, Any]] = []
        invalids: list[dict[str, str]] = []
        duplicates: list[dict[str, str]] = []
        seen_hashes: dict[str, tuple[str, str]] = {}
        summary = self._empty_summary(len(archives))

        for archive_path, metadata in archives:
            self._process_archive(
                archive_path,
                metadata,
                records,
                invalids,
                duplicates,
                seen_hashes,
                summary,
            )

        valid_records = [
            record
            for record in records
            if record["quality_status"] == "VALID" and record["include_in_benchmark"]
        ]
        smoke_ids = self._select_smoke_ids(valid_records)
        full_ids = [record["document_id"] for record in valid_records]
        hard_ids = [record["document_id"] for record in valid_records if self._is_hard_case(record)]
        summary.update(
            smoke_test_count=len(smoke_ids),
            full_benchmark_count=len(full_ids),
            hard_case_count=len(hard_ids),
        )

        if not self.dry_run:
            self._write_outputs(records, duplicates, invalids, smoke_ids, full_ids, hard_ids, summary)
        logger.info("Dataset preparation finished successfully")
        return summary

    def verify_existing_dataset(self) -> dict[str, Any]:
        """Validate existing artifacts without mutating the filesystem."""
        manifest_path = self.manifests_dir / "documents.csv"
        jsonl_path = self.manifests_dir / "documents.jsonl"
        summary_path = self.logs_dir / "summary.json"
        required = [
            manifest_path,
            jsonl_path,
            self.manifests_dir / "duplicates.csv",
            self.splits_dir / "smoke_test.txt",
            self.splits_dir / "benchmark_full.txt",
            self.splits_dir / "hard_cases.txt",
            summary_path,
        ]
        errors = [f"Missing required artifact: {path}" for path in required if not path.is_file()]
        if errors:
            raise ValueError("Dataset verification failed:\n- " + "\n- ".join(errors))

        with manifest_path.open(encoding="utf-8", newline="") as stream:
            records = list(csv.DictReader(stream))
        jsonl_records = [json.loads(line) for line in jsonl_path.read_text(encoding="utf-8").splitlines() if line]
        if len(records) != len(jsonl_records):
            errors.append("documents.csv and documents.jsonl record counts differ")

        ids = [record["document_id"] for record in records]
        if len(ids) != len(set(ids)):
            errors.append("document_id values are not unique")

        benchmark_names = [record["benchmark_filename"] for record in records if record["benchmark_filename"]]
        if len(benchmark_names) != len(set(benchmark_names)):
            errors.append("benchmark filenames are not unique")

        valid_ids: list[str] = []
        valid_hashes: set[str] = set()
        for record in records:
            benchmark_path_text = record.get("benchmark_path", "")
            include = parse_bool(record.get("include_in_benchmark"))
            merged = parse_bool(record.get("is_merged"))
            if include and merged:
                errors.append(f"Merged document included in benchmark: {record['document_id']}")
            if not include:
                continue

            valid_ids.append(record["document_id"])
            sha = record.get("sha256", "")
            if sha in valid_hashes:
                errors.append(f"Duplicate SHA-256 in benchmark: {sha}")
            valid_hashes.add(sha)

            if not benchmark_path_text:
                errors.append(f"Missing benchmark_path: {record['document_id']}")
                continue
            document_path = self.dataset_root / Path(benchmark_path_text)
            if not document_path.is_file():
                errors.append(f"Benchmark PDF missing: {document_path}")
                continue
            if not is_pdf_magic_bytes(document_path):
                errors.append(f"Invalid PDF magic bytes: {document_path}")
                continue
            if compute_sha256(document_path) != sha:
                errors.append(f"SHA-256 mismatch: {record['document_id']}")

        full_ids = read_split(self.splits_dir / "benchmark_full.txt")
        smoke_ids = read_split(self.splits_dir / "smoke_test.txt")
        hard_ids = read_split(self.splits_dir / "hard_cases.txt")
        if full_ids != valid_ids:
            errors.append("benchmark_full.txt does not match ordered valid manifest documents")
        if not set(smoke_ids).issubset(valid_ids):
            errors.append("smoke_test.txt contains unknown or excluded document IDs")
        if not set(hard_ids).issubset(valid_ids):
            errors.append("hard_cases.txt contains unknown or excluded document IDs")

        stored_summary = json.loads(summary_path.read_text(encoding="utf-8"))
        if stored_summary.get("full_benchmark_count") != len(full_ids):
            errors.append("summary full_benchmark_count does not match benchmark_full.txt")
        if stored_summary.get("smoke_test_count") != len(smoke_ids):
            errors.append("summary smoke_test_count does not match smoke_test.txt")
        if stored_summary.get("hard_case_count") != len(hard_ids):
            errors.append("summary hard_case_count does not match hard_cases.txt")

        if errors:
            raise ValueError("Dataset verification failed:\n- " + "\n- ".join(errors))

        return {
            **stored_summary,
            "verification_status": "PASSED",
            "verified_manifest_records": len(records),
            "verified_benchmark_documents": len(valid_ids),
        }

    def _empty_summary(self, archive_count: int) -> dict[str, Any]:
        return {
            "total_archives": archive_count,
            "total_pdf_files_found": 0,
            "individual_pdf_count": 0,
            "merged_reference_count": 0,
            "valid_benchmark_count": 0,
            "duplicate_count": 0,
            "invalid_count": 0,
            "image_only_pdf_count": 0,
            "text_pdf_count": 0,
            "categories": {key: 0 for key in ("vat_discount", "utilities", "sales_receipts")},
            "smoke_test_count": 0,
            "full_benchmark_count": 0,
            "hard_case_count": 0,
        }

    def _prepare_output_directories(self) -> None:
        derived_roots = [self.staging_dir, self.raw_dir, self.ref_merged_dir, self.benchmark_dir]
        if self.overwrite and not self.dry_run:
            for path in derived_roots:
                if path.exists():
                    shutil.rmtree(path)
        if self.dry_run:
            return
        for path in [
            self.archives_dir,
            self.staging_dir,
            self.raw_dir / "invoices",
            self.raw_dir / "unknown",
            self.ref_merged_dir,
            self.documents_dir,
            self.ground_truth_dir,
            self.manifests_dir,
            self.splits_dir,
            self.logs_dir,
        ]:
            path.mkdir(parents=True, exist_ok=True)

    def _collect_archives(self) -> list[tuple[Path, dict[str, str]]]:
        found: list[tuple[Path, dict[str, str]]] = []
        for archive_name, metadata in ARCHIVE_MAPPINGS.items():
            source = self.dataset_root / archive_name
            archived = self.archives_dir / archive_name
            if source.is_file():
                if not self.dry_run and (self.overwrite or not archived.exists()):
                    archived.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source, archived)
                found.append((archived if archived.exists() else source, metadata))
            elif archived.is_file():
                found.append((archived, metadata))
            else:
                logger.warning("Archive not found: %s", archive_name)
        return found

    def _process_archive(
        self,
        archive_path: Path,
        metadata: dict[str, str],
        records: list[dict[str, Any]],
        invalids: list[dict[str, str]],
        duplicates: list[dict[str, str]],
        seen_hashes: dict[str, tuple[str, str]],
        summary: dict[str, Any],
    ) -> None:
        category = metadata["category"]
        staging = self.staging_dir / category
        if not self.dry_run:
            if staging.exists() and self.overwrite:
                shutil.rmtree(staging)
            staging.mkdir(parents=True, exist_ok=True)
            extracted = extract_zip_safely(archive_path, staging)
        else:
            extracted = []

        individual: list[Path] = []
        for path in extracted:
            relative = path.relative_to(staging)
            if path.suffix.casefold() != ".pdf":
                invalids.append(
                    {
                        "source_archive": archive_path.name,
                        "file_path": relative.as_posix(),
                        "reason": "Non-PDF file in archive",
                    }
                )
                summary["invalid_count"] += 1
                continue
            summary["total_pdf_files_found"] += 1
            if is_merged_file(path.name):
                self._record_merged(path, archive_path.name, metadata, records, summary)
            else:
                individual.append(path)

        individual.sort(key=lambda path: (natural_sort_key(path.name), path.as_posix().casefold()))
        sequence = 0
        for path in individual:
            pdf_metadata = inspect_pdf(path)
            if not pdf_metadata["is_valid_pdf"]:
                invalids.append(
                    {
                        "source_archive": archive_path.name,
                        "file_path": path.relative_to(staging).as_posix(),
                        "reason": str(pdf_metadata["error"]),
                    }
                )
                summary["invalid_count"] += 1
                continue

            sequence += 1
            document_id = f"{metadata['prefix']}-{sequence:04d}"
            safe_stem = sanitize_filename(path.stem)
            benchmark_name = f"{category}_{sequence:04d}_{safe_stem}.pdf"
            raw_destination = self.raw_dir / "invoices" / category / path.relative_to(staging)
            benchmark_destination = self.documents_dir / category / benchmark_name
            self._copy_file(path, raw_destination)
            self._copy_file(path, benchmark_destination)

            sha = compute_sha256(path)
            benchmark_relative = benchmark_destination.relative_to(self.dataset_root).as_posix()
            duplicate_of = seen_hashes.get(sha)
            include = duplicate_of is None
            status = "VALID" if include else "DUPLICATE"
            if duplicate_of:
                duplicates.append(
                    {
                        "sha256": sha,
                        "primary_document_id": duplicate_of[0],
                        "duplicate_document_id": document_id,
                        "primary_path": duplicate_of[1],
                        "duplicate_path": benchmark_relative,
                        "reason": "Exact SHA-256 content match",
                    }
                )
                summary["duplicate_count"] += 1
            else:
                seen_hashes[sha] = (document_id, benchmark_relative)
                summary["valid_benchmark_count"] += 1

            summary["individual_pdf_count"] += 1
            summary["categories"][category] += 1
            summary["image_only_pdf_count" if pdf_metadata["is_image_only_pdf"] else "text_pdf_count"] += 1
            records.append(
                {
                    "document_id": document_id,
                    "dataset_category": category,
                    "document_family": metadata["document_family"],
                    "source_group": metadata["source_group"],
                    "source_archive": archive_path.name,
                    "original_filename": path.name,
                    "benchmark_filename": benchmark_name,
                    "raw_path": raw_destination.relative_to(self.dataset_root).as_posix(),
                    "benchmark_path": benchmark_relative,
                    "sha256": sha,
                    "file_size_bytes": path.stat().st_size,
                    "page_count": pdf_metadata["page_count"],
                    "width_points": pdf_metadata["width_points"],
                    "height_points": pdf_metadata["height_points"],
                    "has_text_layer": pdf_metadata["has_text_layer"],
                    "text_character_count": pdf_metadata["text_character_count"],
                    "is_image_only_pdf": pdf_metadata["is_image_only_pdf"],
                    "is_merged": False,
                    "include_in_benchmark": include,
                    "duplicate_of": duplicate_of[0] if duplicate_of else "",
                    "quality_status": status,
                    "ground_truth_level": 0,
                    "notes": "",
                }
            )

    def _record_merged(
        self,
        path: Path,
        archive_name: str,
        metadata: dict[str, str],
        records: list[dict[str, Any]],
        summary: dict[str, Any],
    ) -> None:
        category = metadata["category"]
        destination = self.ref_merged_dir / category / path.name
        self._copy_file(path, destination)
        pdf_metadata = inspect_pdf(path)
        summary["merged_reference_count"] += 1
        records.append(
            {
                "document_id": f"MERGED-{category.upper()}",
                "dataset_category": category,
                "document_family": metadata["document_family"],
                "source_group": metadata["source_group"],
                "source_archive": archive_name,
                "original_filename": path.name,
                "benchmark_filename": f"merged_{path.name}",
                "raw_path": destination.relative_to(self.dataset_root).as_posix(),
                "benchmark_path": "",
                "sha256": compute_sha256(path),
                "file_size_bytes": path.stat().st_size,
                "page_count": pdf_metadata["page_count"],
                "width_points": pdf_metadata["width_points"],
                "height_points": pdf_metadata["height_points"],
                "has_text_layer": pdf_metadata["has_text_layer"],
                "text_character_count": pdf_metadata["text_character_count"],
                "is_image_only_pdf": pdf_metadata["is_image_only_pdf"],
                "is_merged": True,
                "include_in_benchmark": False,
                "duplicate_of": "",
                "quality_status": "MERGED_REFERENCE",
                "ground_truth_level": 0,
                "notes": "Merged reference file containing aggregated pages",
            }
        )

    def _copy_file(self, source: Path, destination: Path) -> None:
        if self.dry_run:
            return
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists() and not self.overwrite:
            return
        if destination.exists():
            destination.unlink()
        if self.copy_mode == "hardlink":
            try:
                os.link(source, destination)
                return
            except OSError as exc:
                logger.debug("Hardlink failed; falling back to copy: %s", exc)
        shutil.copy2(source, destination)

    def _select_smoke_ids(self, records: list[dict[str, Any]]) -> list[str]:
        if self.smoke_size == 0:
            return []
        categories = ("vat_discount", "utilities", "sales_receipts")
        pools = {
            category: [record["document_id"] for record in records if record["dataset_category"] == category]
            for category in categories
        }
        selected: list[str] = []
        while len(selected) < self.smoke_size and any(pools.values()):
            for category in categories:
                if pools[category] and len(selected) < self.smoke_size:
                    selected.append(pools[category].pop(0))
        return selected

    @staticmethod
    def _is_hard_case(record: dict[str, Any]) -> bool:
        return bool(
            record["page_count"] > 1
            or record["is_image_only_pdf"]
            or record["file_size_bytes"] > 500_000
            or (record["width_points"] and abs(record["width_points"] - 595.0) > 50)
        )

    def _write_outputs(
        self,
        records: list[dict[str, Any]],
        duplicates: list[dict[str, str]],
        invalids: list[dict[str, str]],
        smoke_ids: list[str],
        full_ids: list[str],
        hard_ids: list[str],
        summary: dict[str, Any],
    ) -> None:
        self.manifests_dir.mkdir(parents=True, exist_ok=True)
        self.splits_dir.mkdir(parents=True, exist_ok=True)
        self.logs_dir.mkdir(parents=True, exist_ok=True)

        with (self.manifests_dir / "documents.csv").open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=MANIFEST_FIELDS)
            writer.writeheader()
            writer.writerows(records)
        with (self.manifests_dir / "documents.jsonl").open("w", encoding="utf-8") as stream:
            for record in records:
                stream.write(json.dumps(record, ensure_ascii=False) + "\n")

        duplicate_fields = [
            "sha256",
            "primary_document_id",
            "duplicate_document_id",
            "primary_path",
            "duplicate_path",
            "reason",
        ]
        with (self.manifests_dir / "duplicates.csv").open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=duplicate_fields)
            writer.writeheader()
            writer.writerows(duplicates)
        with (self.logs_dir / "invalid_files.csv").open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=["source_archive", "file_path", "reason"])
            writer.writeheader()
            writer.writerows(invalids)

        for filename, ids in (
            ("smoke_test.txt", smoke_ids),
            ("benchmark_full.txt", full_ids),
            ("hard_cases.txt", hard_ids),
        ):
            text = "\n".join(ids)
            (self.splits_dir / filename).write_text(text + ("\n" if text else ""), encoding="utf-8")
        (self.logs_dir / "summary.json").write_text(
            json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Benchmark Dataset Preparation Tool")
    parser.add_argument("--dataset-root", default=r"D:\Documents-engine\datasets")
    parser.add_argument("--overwrite-derived", action="store_true")
    parser.add_argument("--verify-only", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    parser.add_argument("--smoke-size", type=int, default=10)
    parser.add_argument("--copy-mode", choices=["copy", "hardlink"], default="copy")
    args = parser.parse_args()

    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stdout)]
    if not args.verify_only:
        log_dir = Path(args.dataset_root) / "preparation_logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        handlers.insert(0, logging.FileHandler(log_dir / "preparation.log", encoding="utf-8"))
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=handlers,
    )

    preparer = DatasetPreparer(
        dataset_root=Path(args.dataset_root),
        overwrite_derived=args.overwrite_derived,
        dry_run=args.dry_run,
        verify_only=args.verify_only,
        smoke_size=args.smoke_size,
        copy_mode=args.copy_mode,
    )
    try:
        summary = preparer.run()
    except Exception as exc:
        logger.error("%s", exc)
        raise SystemExit(1) from exc
    print("=== Dataset Preparation Summary ===")
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
