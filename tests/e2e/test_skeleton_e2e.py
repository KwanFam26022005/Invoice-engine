"""End-to-end integration tests for the benchmark controller and worker."""

import json
import tempfile
from pathlib import Path

from document_benchmark.core.contracts import BenchmarkRunSpec, DocumentInput, EngineSpec
from document_benchmark.core.engine_registry import registry
from document_benchmark.runner.benchmark_controller import BenchmarkController


def test_skeleton_benchmark_e2e() -> None:
    with tempfile.TemporaryDirectory(prefix="bm_e2e_test_") as tmp_dir:
        tmp_path = Path(tmp_dir)
        registry.register_config(
            EngineSpec(
                engine_id="mock",
                config_id="mock_e2e_config",
                options={
                    "prepare_delay_ms": 5,
                    "extract_delay_ms": 10,
                    "mock_family": "invoice",
                },
            )
        )

        document = DocumentInput(
            document_id="doc_invoice_e2e",
            path="datasets/documents/sample_invoice.pdf",
            filename="sample_invoice.pdf",
            sha256="abc123e2e",
            page_count=1,
        )
        run_id = "run_e2e_test_001"
        run_spec = BenchmarkRunSpec(
            run_id=run_id,
            document_ids=[document.document_id],
            engine_config_ids=["mock_e2e_config"],
            warmup_runs=1,
            measured_runs=2,
            timeout_seconds=10,
        )

        summary = BenchmarkController(runs_root=str(tmp_path / "runs")).run_benchmark(
            spec=run_spec,
            documents=[document],
        )

        assert summary["status"] == "COMPLETED"
        assert summary["completed_tasks"] == 3
        assert summary["successful_measured_runs"] == 2
        assert summary["failed_measured_runs"] == 0
        assert summary["skipped_tasks"] == 0

        run_dir = tmp_path / "runs" / run_id
        assert (run_dir / "run_config.yaml").exists()
        assert (run_dir / "environment.json").exists()
        assert (run_dir / "manifest.csv").exists()
        assert (run_dir / "status.json").exists()

        raw_dir = run_dir / "raw_outputs" / "mock_e2e_config" / "doc_invoice_e2e"
        assert not (raw_dir / "run_001.json").exists()
        assert (raw_dir / "run_002.json").exists()
        assert (raw_dir / "run_003.json").exists()

        raw_data = json.loads((raw_dir / "run_003.json").read_text(encoding="utf-8"))
        assert raw_data["success"] is True
        assert raw_data["engine_id"] == "mock"
        assert "invoice_number" in raw_data["field_candidates"]


def test_incompatible_track_is_skipped_before_worker_start() -> None:
    with tempfile.TemporaryDirectory(prefix="bm_skip_test_") as tmp_dir:
        tmp_path = Path(tmp_dir)
        config_id = "mock_native_only"
        registry.register_config(
            EngineSpec(
                engine_id="mock",
                config_id=config_id,
                supports_pdf_text=True,
                supports_scanned_pdf=False,
                options={"benchmark_track": "native_pdf"},
            )
        )
        document = DocumentInput(
            document_id="scan_document",
            path="scan.pdf",
            filename="scan.pdf",
            sha256="scan",
            metadata={
                "input_profile": "scan_ocr",
                "is_image_only_pdf": True,
                "has_text_layer": False,
            },
        )
        summary = BenchmarkController(runs_root=str(tmp_path / "runs")).run_benchmark(
            spec=BenchmarkRunSpec(
                run_id="run_skip_test",
                document_ids=[document.document_id],
                engine_config_ids=[config_id],
                warmup_runs=1,
                measured_runs=2,
            ),
            documents=[document],
        )

        assert summary["status"] == "FAILED"
        assert summary["skipped_tasks"] == 1
        assert summary["successful_measured_runs"] == 0
        assert summary["failed_measured_runs"] == 0
        assert summary["results"][0]["status"] == "SKIPPED"
        assert summary["results"][0]["error_type"] == "UnsupportedBenchmarkInput"
        raw_outputs = tmp_path / "runs" / "run_skip_test" / "raw_outputs"
        assert raw_outputs.exists()
        assert not any(raw_outputs.rglob("*.json"))
