"""Command Line Interface for running Document Engine Benchmarks."""

import argparse
import hashlib
import sys
import uuid
from pathlib import Path

from document_benchmark.core.contracts import BenchmarkRunSpec, DocumentInput
from document_benchmark.core.engine_registry import registry
from document_benchmark.runner.benchmark_controller import BenchmarkController


def compute_sha256(file_path: Path) -> str:
    h = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(8192):
            h.update(chunk)
    return h.hexdigest()


def get_pdf_page_count(file_path: Path) -> int:
    try:
        from pypdf import PdfReader

        reader = PdfReader(str(file_path))
        return len(reader.pages)
    except Exception:
        return 1


def load_engine_configs(configs_dir: Path) -> None:
    if not configs_dir.exists():
        return
    for yaml_file in configs_dir.glob("*.yaml"):
        try:
            registry.load_config_from_file(str(yaml_file))
        except Exception as e:
            sys.stderr.write(f"Warning: Failed to load config {yaml_file}: {e}\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Document Engine Benchmark CLI")
    parser.add_argument(
        "--pdfs",
        nargs="+",
        help="Path to input PDF files",
    )
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
    parser.add_argument(
        "--warmup-runs",
        type=int,
        default=1,
        help="Number of warmup runs",
    )
    parser.add_argument(
        "--measured-runs",
        type=int,
        default=2,
        help="Number of measured runs",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=60,
        help="Execution timeout per document in seconds",
    )
    parser.add_argument(
        "--runs-root",
        default="runs",
        help="Root directory for saving run artifacts",
    )

    args = parser.parse_args()

    # Load engine configs
    configs_path = Path(args.configs_dir)
    load_engine_configs(configs_path)

    # Process input documents
    doc_inputs: list[DocumentInput] = []
    if args.pdfs:
        for p_str in args.pdfs:
            p = Path(p_str)
            if not p.exists():
                sys.stderr.write(f"PDF file not found: {p}\n")
                continue
            doc_id = f"doc_{p.stem}_{hashlib.md5(p_str.encode()).hexdigest()[:6]}"
            sha = compute_sha256(p)
            pgs = get_pdf_page_count(p)
            doc_inputs.append(
                DocumentInput(
                    document_id=doc_id,
                    path=str(p.resolve()),
                    filename=p.name,
                    sha256=sha,
                    page_count=pgs,
                )
            )

    if not doc_inputs:
        sys.stderr.write("No valid PDF inputs provided. Exiting.\n")
        sys.exit(1)

    run_id = f"run_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
    spec = BenchmarkRunSpec(
        run_id=run_id,
        document_ids=[d.document_id for d in doc_inputs],
        engine_config_ids=args.engines,
        timeout_seconds=args.timeout,
        warmup_runs=args.warmup_runs,
        measured_runs=args.measured_runs,
    )

    controller = BenchmarkController(runs_root=args.runs_root)

    print(f"=== Starting Benchmark Run: {run_id} ===")
    print(f"Documents ({len(doc_inputs)}): {[d.filename for d in doc_inputs]}")
    print(f"Engine Configs: {args.engines}")

    def on_progress(p: dict):
        print(
            f" Progress: Config={p['config_id']} Doc={p['filename']} Run={p['run_index']} Warmup={p['is_warmup']}"
        )

    summary = controller.run_benchmark(
        spec=spec, documents=doc_inputs, progress_callback=on_progress
    )

    print(f"=== Benchmark Completed: {summary['status']} ===")
    print(f"Completed Tasks: {summary['completed_tasks']}")
    print(f"Run Artifacts saved to: {Path(args.runs_root) / run_id}")


from datetime import datetime, timezone

if __name__ == "__main__":
    main()
