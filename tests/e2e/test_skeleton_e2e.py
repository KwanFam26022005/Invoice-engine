"""End-to-end integration test for benchmark controller and isolated worker skeleton."""

import json
import tempfile
from pathlib import Path

from document_benchmark.core.contracts import BenchmarkRunSpec, DocumentInput, EngineSpec
from document_benchmark.core.engine_registry import registry
from document_benchmark.runner.benchmark_controller import BenchmarkController


def test_skeleton_benchmark_e2e():
    with tempfile.TemporaryDirectory(prefix="bm_e2e_test_") as tmp_dir:
        tmp_path = Path(tmp_dir)

        # 1. Register Mock engine spec
        spec_cfg = EngineSpec(
            engine_id="mock",
            config_id="mock_e2e_config",
            options={
                "prepare_delay_ms": 5,
                "extract_delay_ms": 10,
                "mock_family": "invoice",
            },
        )
        registry.register_config(spec_cfg)

        # 2. Input document
        doc = DocumentInput(
            document_id="doc_invoice_e2e",
            path="datasets/documents/sample_invoice.pdf",
            filename="sample_invoice.pdf",
            sha256="abc123e2e",
            page_count=1,
        )

        run_id = "run_e2e_test_001"
        run_spec = BenchmarkRunSpec(
            run_id=run_id,
            document_ids=[doc.document_id],
            engine_config_ids=["mock_e2e_config"],
            warmup_runs=1,
            measured_runs=2,
            timeout_seconds=10,
        )

        controller = BenchmarkController(runs_root=str(tmp_path / "runs"))
        summary = controller.run_benchmark(spec=run_spec, documents=[doc])

        # 3. Assert status and outputs
        assert summary["status"] == "COMPLETED"
        assert summary["completed_tasks"] == 3  # 1 warmup + 2 measured

        run_dir = tmp_path / "runs" / run_id
        assert (run_dir / "run_config.yaml").exists()
        assert (run_dir / "environment.json").exists()
        assert (run_dir / "manifest.csv").exists()
        assert (run_dir / "status.json").exists()

        raw_output = run_dir / "raw_outputs" / "mock_e2e_config" / "doc_invoice_e2e.json"
        assert raw_output.exists()

        with open(raw_output, "r", encoding="utf-8") as f:
            raw_data = json.load(f)

        assert raw_data["success"] is True
        assert raw_data["engine_id"] == "mock"
        assert "invoice_number" in raw_data["field_candidates"]
