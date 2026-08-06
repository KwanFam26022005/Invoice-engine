"""Command line interface for local document-engine benchmarks."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import sys
import uuid
from pathlib import Path
from typing import Any

from document_benchmark.core.contracts import BenchmarkRunSpec, DocumentInput
from document_benchmark.core.engine_registry import registry
from document_benchmark.runner.benchmark_controller import BenchmarkController


def compute_sha256(file_path: Path) -> str:
    digest = hashlib.sha256()
    with file_path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(8192), b""):
            digest.update(chunk)
    return digest.hexdigest()


def inspect_pdf_profile(file_path: Path) -> tuple[int, dict[str, Any]]:
    """Inspect the native PDF text layer without OCR."""
    try:
        from pypdf import PdfReader

        reader = PdfReader(str(file_path))
        text_character_count = 0
        for page in reader.pages:
            try:
                text_character_count += len((page.extract_text() or "").strip())
            except Exception:
                continue
        has_text_layer = text_character_count >= 50
        metadata = {
            "has_text_layer": has_text_layer,
            "text_character_count": text_character_count,
            "is_image_only_pdf": not has_text_layer,
            "input_profile": "native_pdf" if has_text_layer else "scan_ocr",
        }
        return len(reader.pages), metadata
    except Exception as exc:
        return 1, {
            "has_text_layer": None,
            "text_character_count": None,
            "is_image_only_pdf": None,
            "input_profile": None,
            "inspection_warning": str(exc),
        }


def load_engine_configs(configs_dir: Path) -> None:
    if not configs_dir.exists():
        return
    for yaml_file in sorted(configs_dir.glob("*.yaml")):
        try:
            registry.load_config_from_file(str(yaml_file))
        except Exception as exc:
            sys.stderr.write(f"Warning: Failed to load config {yaml_file}: {exc}\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Document Engine Benchmark CLI")
    parser.add_argument("--pdfs", nargs="+", help="Path to input PDF files")
    parser.add_argument(
        "--configs-dir",
        default="configs/engines",
        help="Directory containing engine YAML configs",
    )
    parser.add_argument(
        "--engines",
        nargs="+",
        default=["mock_default"],
        help="Engine config_ids to benchmark",
    )
    parser.add_argument("--warmup-runs", type=int, default=1)
    parser.add_argument("--measured-runs", type=int, default=2)
    parser.add_argument("--timeout", type=int, default=60)
    parser.add_argument("--runs-root", default="runs")
    args = parser.parse_args()

    load_engine_configs(Path(args.configs_dir))

    documents: list[DocumentInput] = []
    for path_value in args.pdfs or []:
        path = Path(path_value)
        if not path.exists():
            sys.stderr.write(f"PDF file not found: {path}\n")
            continue
        page_count, metadata = inspect_pdf_profile(path)
        document_id = f"doc_{path.stem}_{hashlib.md5(path_value.encode()).hexdigest()[:6]}"
        documents.append(
            DocumentInput(
                document_id=document_id,
                path=str(path.resolve()),
                filename=path.name,
                sha256=compute_sha256(path),
                page_count=page_count,
                metadata=metadata,
            )
        )

    if not documents:
        sys.stderr.write("No valid PDF inputs provided. Exiting.\n")
        raise SystemExit(1)

    run_id = f"run_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
    run_spec = BenchmarkRunSpec(
        run_id=run_id,
        document_ids=[document.document_id for document in documents],
        engine_config_ids=args.engines,
        timeout_seconds=args.timeout,
        warmup_runs=args.warmup_runs,
        measured_runs=args.measured_runs,
    )
    controller = BenchmarkController(runs_root=args.runs_root)

    print(f"=== Starting Benchmark Run: {run_id} ===")
    print(f"Documents ({len(documents)}): {[document.filename for document in documents]}")
    print(f"Input profiles: {[document.metadata.get('input_profile') for document in documents]}")
    print(f"Engine Configs: {args.engines}")

    def on_progress(progress: dict[str, Any]) -> None:
        print(
            " Progress: "
            f"Config={progress['config_id']} "
            f"Doc={progress['filename']} "
            f"Run={progress['run_index']} "
            f"Warmup={progress['is_warmup']} "
            f"Status={progress['status']}"
        )
        if progress.get("message"):
            print(f"  Reason: {progress['message']}")

    summary = controller.run_benchmark(
        spec=run_spec,
        documents=documents,
        progress_callback=on_progress,
    )
    print(f"=== Benchmark Completed: {summary['status']} ===")
    print(f"Completed Tasks: {summary['completed_tasks']}")
    print(f"Skipped Tasks: {summary.get('skipped_tasks', 0)}")
    print(f"Run Artifacts saved to: {Path(args.runs_root) / run_id}")


if __name__ == "__main__":
    main()
