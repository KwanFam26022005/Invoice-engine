"""End-to-end integration test for the benchmark controller and isolated worker."""

import json
import tempfile
from pathlib import Path

from document_benchmark.core.contracts import BenchmarkRunSpec, DocumentInput, EngineSpec
from document_benchmark.core.engine_registry import registry
from document_benchmark.runner.benchmark_controller import BenchmarkController


def test_skeleton_benchmark_e2e():
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

        run_dir = tmp_path / "runs" / run_id
        assert (run_dir / "run_config.yaml").exists()
        assert (run_dir / "environment.json").exists()
        assert (run_dir / "manifest.csv").exists()
        assert (run_dir / "status.json").exists()

        raw_dir = run_dir / "raw_outputs" / "mock_e2e_config" / "doc_invoice_e2e"
        assert not (raw_dir / "run_001.json").exists()  # warm-up is not persisted
        assert (raw_dir / "run_002.json").exists()
        assert (raw_dir / "run_003.json").exists()

        raw_data = json.loads((raw_dir / "run_003.json").read_text(encoding="utf-8"))
        assert raw_data["success"] is True
        assert raw_data["engine_id"] == "mock"
        assert "invoice_number" in raw_data["field_candidates"]
