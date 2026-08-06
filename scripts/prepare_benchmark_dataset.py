"""Benchmark dataset preparation pipeline for Document Extraction Engine Benchmark.

Extracts, inspects, normalizes, and structures PDF document datasets from raw archive ZIPs.
Generates manifests, splits, logs, and summary reports.
"""

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
from typing import Any, Dict, Tuple
import zipfile

import fitz  # PyMuPDF


# Configure logger
logger = logging.getLogger("dataset_preparation")


# Archive mappings
ARCHIVE_MAPPINGS: Dict[str, Dict[str, str]] = {
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


def natural_sort_key(s: str) -> list[Any]:
    """Natural sort key splitting digits and text strings."""
    return [int(text) if text.isdigit() else text.lower() for text in re.split(r"(\d+)", str(s))]


def sanitize_filename(filename: str) -> str:
    """Sanitize filename to be safe on Windows filesystems."""
    name = Path(filename).name
    # Replace invalid Windows chars \ / : * ? " < > | and spaces/ctrl chars
    sanitized = re.sub(r'[\\/*?:"<>|\s]', "_", name)
    sanitized = re.sub(r"_+", "_", sanitized).strip("_")
    return sanitized or "document.pdf"


def compute_sha256(file_path: Path) -> str:
    """Compute SHA-256 hash of a file."""
    h = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def is_pdf_magic_bytes(file_path: Path) -> bool:
    """Check if file starts with PDF magic bytes %PDF."""
    try:
        with open(file_path, "rb") as f:
            header = f.read(4)
            return header.startswith(b"%PDF")
    except Exception:
        return False


def is_safe_zip_path(target_dir: Path, extracted_path: Path) -> bool:
    """Prevent Zip Slip / Path Traversal vulnerabilities."""
    try:
        resolved_target = target_dir.resolve()
        resolved_extracted = extracted_path.resolve()
        return str(resolved_extracted).startswith(str(resolved_target))
    except Exception:
        return False


def extract_zip_safely(zip_path: Path, extract_dir: Path) -> list[Path]:
    """Extract zip file securely and return list of extracted file paths."""
    extracted_files: list[Path] = []
    with zipfile.ZipFile(zip_path, "r") as z:
        for member in z.infolist():
            if member.is_dir():
                continue
            target_path = extract_dir / member.filename
            if not is_safe_zip_path(extract_dir, target_path):
                logger.warning(f"Zip slip attempt detected and blocked: {member.filename}")
                continue
            target_path.parent.mkdir(parents=True, exist_ok=True)
            with z.open(member) as src, open(target_path, "wb") as dst:
                shutil.copyfileobj(src, dst)
            extracted_files.append(target_path)
    return extracted_files


def inspect_pdf(file_path: Path) -> Dict[str, Any]:
    """Inspect PDF properties (page count, dimensions, text character count)."""
    res = {
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
        res["error"] = "Invalid PDF magic bytes"
        return res

    try:
        doc = fitz.open(str(file_path))
        res["is_valid_pdf"] = True
        res["page_count"] = len(doc)

        if len(doc) > 0:
            page0 = doc[0]
            rect = page0.rect
            res["width_points"] = round(rect.width, 2)
            res["height_points"] = round(rect.height, 2)

        total_text_chars = 0
        for page in doc:
            txt = page.get_text()
            total_text_chars += len(txt.strip())

        res["text_character_count"] = total_text_chars
        res["has_text_layer"] = total_text_chars >= 50
        res["is_image_only_pdf"] = total_text_chars < 50
        doc.close()
    except Exception as e:
        res["is_valid_pdf"] = False
        res["error"] = str(e)

    return res


def is_merged_file(filename: str) -> bool:
    """Check if file is a merged reference PDF."""
    fname_lower = filename.lower()
    return "merged" in fname_lower or fname_lower.endswith("_merged.pdf")


class DatasetPreparer:
    """Main preparation pipeline manager."""

    def __init__(
        self,
        dataset_root: Path,
        overwrite_derived: bool = False,
        dry_run: bool = False,
        verify_only: bool = False,
        smoke_size: int = 10,
        copy_mode: str = "copy",
    ) -> None:
        self.dataset_root = dataset_root.resolve()
        self.overwrite = overwrite_derived
        self.dry_run = dry_run
        self.verify_only = verify_only
        self.smoke_size = smoke_size
        self.copy_mode = copy_mode

        # Define directory structure
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

    def setup_directories(self) -> None:
        """Create all required directories."""
        if self.dry_run:
            logger.info("[DRY RUN] Would create target directories.")
            return

        dirs = [
            self.archives_dir,
            self.staging_dir,
            self.raw_dir / "invoices" / "vat_discount",
            self.raw_dir / "invoices" / "utilities",
            self.raw_dir / "invoices" / "sales_receipts",
            self.raw_dir / "unknown",
            self.ref_merged_dir / "vat_discount",
            self.ref_merged_dir / "utilities",
            self.ref_merged_dir / "sales_receipts",
            self.documents_dir / "vat_discount",
            self.documents_dir / "utilities",
            self.documents_dir / "sales_receipts",
            self.ground_truth_dir,
            self.manifests_dir,
            self.splits_dir,
            self.logs_dir,
        ]
        for d in dirs:
            d.mkdir(parents=True, exist_ok=True)

    def archive_zip_files(self) -> list[Tuple[Path, Dict[str, str]]]:
        """Move or copy raw ZIP files into archives directory."""
        found_archives: list[Tuple[Path, Dict[str, str]]] = []
        for zip_name, meta in ARCHIVE_MAPPINGS.items():
            src_zip = self.dataset_root / zip_name
            target_zip = self.archives_dir / zip_name

            if src_zip.exists():
                if not self.dry_run and not target_zip.exists():
                    shutil.copy2(src_zip, target_zip)
                    logger.info(f"Copied {zip_name} to archives/")
                found_archives.append((target_zip if target_zip.exists() else src_zip, meta))
            elif target_zip.exists():
                found_archives.append((target_zip, meta))
            else:
                logger.warning(f"Archive zip not found in root or archives: {zip_name}")

        return found_archives

    def copy_file(self, src: Path, dst: Path) -> None:
        """Copy file using copy or hardlink based on config."""
        if self.dry_run:
            return
        dst.parent.mkdir(parents=True, exist_ok=True)
        if self.copy_mode == "hardlink":
            try:
                if dst.exists():
                    dst.unlink()
                os.link(src, dst)
                return
            except Exception as e:
                logger.debug(f"Hardlink failed ({e}), falling back to copy.")

        shutil.copy2(src, dst)

    def run(self) -> Dict[str, Any]:
        """Execute full dataset preparation pipeline."""
        logger.info(f"Starting dataset preparation at {self.dataset_root}")
        self.setup_directories()

        archives = self.archive_zip_files()
        if not archives:
            logger.error("No valid ZIP archives found to process. Exiting.")
            return {}

        invalid_records: list[Dict[str, Any]] = []
        all_manifest_records: list[Dict[str, Any]] = []
        duplicate_records: list[Dict[str, Any]] = []
        seen_sha256: Dict[str, str] = {}  # sha256 -> primary_document_id

        summary_counts = {
            "total_archives": len(archives),
            "total_pdf_files_found": 0,
            "individual_pdf_count": 0,
            "merged_reference_count": 0,
            "valid_benchmark_count": 0,
            "duplicate_count": 0,
            "invalid_count": 0,
            "image_only_pdf_count": 0,
            "text_pdf_count": 0,
            "categories": {"vat_discount": 0, "utilities": 0, "sales_receipts": 0},
            "smoke_test_count": 0,
            "full_benchmark_count": 0,
            "hard_case_count": 0,
        }

        # 1. Process each archive
        for archive_path, meta in archives:
            cat = meta["category"]
            prefix = meta["prefix"]
            source_group = meta["source_group"]
            doc_family = meta["document_family"]
            archive_filename = archive_path.name

            cat_staging = self.staging_dir / cat
            cat_staging.mkdir(parents=True, exist_ok=True)

            logger.info(f"Extracting archive: {archive_filename} -> staging/{cat}")
            if not self.dry_run:
                extracted_paths = extract_zip_safely(archive_path, cat_staging)
            else:
                extracted_paths = []

            # Collect extracted files if dry-run or verify-only
            if not extracted_paths and cat_staging.exists():
                extracted_paths = [p for p in cat_staging.rglob("*") if p.is_file()]

            # Separate PDFs and Non-PDFs
            individual_pdf_paths: list[Path] = []

            for p in extracted_paths:
                rel_path = p.relative_to(cat_staging)

                if p.is_dir():
                    continue

                if not p.name.lower().endswith(".pdf"):
                    invalid_records.append(
                        {
                            "source_archive": archive_filename,
                            "file_path": str(rel_path),
                            "reason": "Non-PDF file in archive",
                        }
                    )
                    summary_counts["invalid_count"] += 1
                    continue

                summary_counts["total_pdf_files_found"] += 1

                # Check merged reference files
                if is_merged_file(p.name):
                    summary_counts["merged_reference_count"] += 1
                    ref_dst = self.ref_merged_dir / cat / p.name
                    self.copy_file(p, ref_dst)

                    # Compute SHA256 & inspect for manifest entry
                    sha = compute_sha256(p) if p.exists() else ""
                    pdf_meta = inspect_pdf(p) if p.exists() else {}

                    all_manifest_records.append(
                        {
                            "document_id": f"MERGED-{cat.upper()}",
                            "dataset_category": cat,
                            "document_family": doc_family,
                            "source_group": source_group,
                            "source_archive": archive_filename,
                            "original_filename": p.name,
                            "benchmark_filename": f"merged_{p.name}",
                            "raw_path": (self.ref_merged_dir / cat / p.name).relative_to(self.dataset_root).as_posix(),
                            "benchmark_path": "",
                            "sha256": sha,
                            "file_size_bytes": p.stat().st_size if p.exists() else 0,
                            "page_count": pdf_meta.get("page_count", 0),
                            "width_points": pdf_meta.get("width_points", 0.0),
                            "height_points": pdf_meta.get("height_points", 0.0),
                            "has_text_layer": pdf_meta.get("has_text_layer", False),
                            "text_character_count": pdf_meta.get("text_character_count", 0),
                            "is_image_only_pdf": pdf_meta.get("is_image_only_pdf", True),
                            "is_merged": True,
                            "include_in_benchmark": False,
                            "duplicate_of": "",
                            "quality_status": "MERGED_REFERENCE",
                            "ground_truth_level": 0,
                            "notes": "Merged reference file containing aggregated pages",
                        }
                    )
                    continue

                # Copy raw files
                raw_dst = self.raw_dir / "invoices" / cat / rel_path
                self.copy_file(p, raw_dst)
                individual_pdf_paths.append(p)

            # Sort individual PDFs using natural sort for deterministic ordering
            individual_pdf_paths.sort(key=lambda path: natural_sort_key(path.name))

            seq = 0
            for p in individual_pdf_paths:
                pdf_meta = inspect_pdf(p) if p.exists() else {}
                if not pdf_meta.get("is_valid_pdf", False):
                    invalid_records.append(
                        {
                            "source_archive": archive_filename,
                            "file_path": p.relative_to(cat_staging).as_posix(),
                            "reason": pdf_meta.get("error", "Invalid PDF format or magic bytes"),
                        }
                    )
                    summary_counts["invalid_count"] += 1
                    continue

                seq += 1
                summary_counts["individual_pdf_count"] += 1
                summary_counts["categories"][cat] += 1

                doc_id = f"{prefix}-{seq:04d}"
                orig_stem = Path(p.name).stem
                safe_stem = sanitize_filename(orig_stem)
                bench_filename = f"{cat}_{seq:04d}_{safe_stem}.pdf"

                bench_dst = self.documents_dir / cat / bench_filename
                self.copy_file(p, bench_dst)

                sha = compute_sha256(p)
                file_size = p.stat().st_size if p.exists() else 0

                if pdf_meta.get("is_image_only_pdf", True):
                    summary_counts["image_only_pdf_count"] += 1
                else:
                    summary_counts["text_pdf_count"] += 1

                # Check duplicate SHA-256
                is_duplicate = sha in seen_sha256
                duplicate_of = seen_sha256.get(sha, "")

                if is_duplicate:
                    summary_counts["duplicate_count"] += 1
                    quality_status = "DUPLICATE"
                    include_in_benchmark = False
                    duplicate_records.append(
                        {
                            "sha256": sha,
                            "primary_document_id": duplicate_of,
                            "duplicate_document_id": doc_id,
                            "primary_path": str(seen_sha256[sha]),
                            "duplicate_path": bench_dst.relative_to(self.dataset_root).as_posix(),
                            "reason": "Exact SHA-256 content match",
                        }
                    )
                else:
                    seen_sha256[sha] = doc_id
                    quality_status = "VALID"
                    include_in_benchmark = True
                    summary_counts["valid_benchmark_count"] += 1

                raw_rel_path = (self.raw_dir / "invoices" / cat / p.relative_to(cat_staging)).relative_to(self.dataset_root).as_posix()
                bench_rel_path = bench_dst.relative_to(self.dataset_root).as_posix()

                all_manifest_records.append(
                    {
                        "document_id": doc_id,
                        "dataset_category": cat,
                        "document_family": doc_family,
                        "source_group": source_group,
                        "source_archive": archive_filename,
                        "original_filename": p.name,
                        "benchmark_filename": bench_filename,
                        "raw_path": raw_rel_path,
                        "benchmark_path": bench_rel_path,
                        "sha256": sha,
                        "file_size_bytes": file_size,
                        "page_count": pdf_meta.get("page_count", 1),
                        "width_points": pdf_meta.get("width_points", 0.0),
                        "height_points": pdf_meta.get("height_points", 0.0),
                        "has_text_layer": pdf_meta.get("has_text_layer", False),
                        "text_character_count": pdf_meta.get("text_character_count", 0),
                        "is_image_only_pdf": pdf_meta.get("is_image_only_pdf", True),
                        "is_merged": False,
                        "include_in_benchmark": include_in_benchmark,
                        "duplicate_of": duplicate_of,
                        "quality_status": quality_status,
                        "ground_truth_level": 0,
                        "notes": "",
                    }
                )

        # 2. Build Benchmark Splits
        valid_benchmark_docs = [
            r for r in all_manifest_records if r["include_in_benchmark"] and r["quality_status"] == "VALID"
        ]

        # smoke_test.txt: max 2 vat_discount, 3 utilities, 5 sales_receipts
        smoke_vat = [r["document_id"] for r in valid_benchmark_docs if r["dataset_category"] == "vat_discount"][:2]
        smoke_util = [r["document_id"] for r in valid_benchmark_docs if r["dataset_category"] == "utilities"][:3]
        smoke_sale = [r["document_id"] for r in valid_benchmark_docs if r["dataset_category"] == "sales_receipts"][:5]
        smoke_ids = smoke_vat + smoke_util + smoke_sale
        summary_counts["smoke_test_count"] = len(smoke_ids)

        # benchmark_full.txt: all valid benchmark docs
        full_ids = [r["document_id"] for r in valid_benchmark_docs]
        summary_counts["full_benchmark_count"] = len(full_ids)

        # hard_cases.txt: multi-page, image-only, large file, non-standard dims
        hard_ids = []
        for r in valid_benchmark_docs:
            if (
                r["page_count"] > 1
                or r["is_image_only_pdf"]
                or r["file_size_bytes"] > 500_000
                or (r["width_points"] > 0 and abs(r["width_points"] - 595.0) > 50)
            ):
                hard_ids.append(r["document_id"])
        summary_counts["hard_case_count"] = len(hard_ids)

        # 3. Write Manifests and Logs to disk
        if not self.dry_run:
            self._write_manifests_and_logs(
                all_manifest_records,
                duplicate_records,
                invalid_records,
                smoke_ids,
                full_ids,
                hard_ids,
                summary_counts,
            )

        logger.info("Dataset preparation finished successfully.")
        return summary_counts

    def _write_manifests_and_logs(
        self,
        all_records: list[Dict[str, Any]],
        duplicates: list[Dict[str, Any]],
        invalids: list[Dict[str, Any]],
        smoke_ids: list[str],
        full_ids: list[str],
        hard_ids: list[str],
        summary: Dict[str, Any],
    ) -> None:
        # documents.csv
        csv_file = self.manifests_dir / "documents.csv"
        fieldnames = [
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
        with open(csv_file, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for r in all_records:
                writer.writerow(r)

        # documents.jsonl
        jsonl_file = self.manifests_dir / "documents.jsonl"
        with open(jsonl_file, "w", encoding="utf-8") as f:
            for r in all_records:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")

        # duplicates.csv
        dup_file = self.manifests_dir / "duplicates.csv"
        dup_fieldnames = [
            "sha256",
            "primary_document_id",
            "duplicate_document_id",
            "primary_path",
            "duplicate_path",
            "reason",
        ]
        with open(dup_file, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=dup_fieldnames)
            writer.writeheader()
            for d in duplicates:
                writer.writerow(d)

        # invalid_files.csv
        inv_file = self.logs_dir / "invalid_files.csv"
        with open(inv_file, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=["source_archive", "file_path", "reason"])
            writer.writeheader()
            for i in invalids:
                writer.writerow(i)

        # Splits text files
        with open(self.splits_dir / "smoke_test.txt", "w", encoding="utf-8") as f:
            f.write("\n".join(smoke_ids) + "\n")

        with open(self.splits_dir / "benchmark_full.txt", "w", encoding="utf-8") as f:
            f.write("\n".join(full_ids) + "\n")

        with open(self.splits_dir / "hard_cases.txt", "w", encoding="utf-8") as f:
            f.write("\n".join(hard_ids) + "\n")

        # summary.json
        with open(self.logs_dir / "summary.json", "w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2, ensure_ascii=False)


def main() -> None:
    parser = argparse.ArgumentParser(description="Benchmark Dataset Preparation Tool")
    parser.add_argument(
        "--dataset-root",
        default=r"D:\Documents-engine\datasets",
        help="Root directory of dataset archives and benchmark outputs",
    )
    parser.add_argument(
        "--overwrite-derived",
        action="store_true",
        help="Overwrite derived staging, raw, reference_merged, and benchmark folders",
    )
    parser.add_argument(
        "--verify-only",
        action="store_true",
        help="Verify existing dataset layout and integrity without extracting/writing files",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Perform dry run without writing modifications to disk",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging verbosity level",
    )
    parser.add_argument(
        "--smoke-size",
        type=int,
        default=10,
        help="Maximum documents to include in smoke_test.txt split",
    )
    parser.add_argument(
        "--copy-mode",
        choices=["copy", "hardlink"],
        default="copy",
        help="File duplication mechanism (copy or hardlink)",
    )

    args = parser.parse_args()

    # Configure logging
    log_level = getattr(logging, args.log_level.upper(), logging.INFO)
    log_dir = Path(args.dataset_root) / "preparation_logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "preparation.log"

    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[
            logging.FileHandler(log_file, encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
    )

    preparer = DatasetPreparer(
        dataset_root=Path(args.dataset_root),
        overwrite_derived=args.overwrite_derived,
        dry_run=args.dry_run,
        verify_only=args.verify_only,
        smoke_size=args.smoke_size,
        copy_mode=args.copy_mode,
    )

    summary = preparer.run()
    print("=== Dataset Preparation Summary ===")
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
