"""Tests for smoke campaign reporting and correctness indexing."""

from __future__ import annotations

import csv
import json
from pathlib import Path

from document_benchmark.smoke.report import write_campaign_reports


def test_report_separates_correctness_from_performance_repeats(tmp_path: Path) -> None:
    campaign_dir = tmp_path / "smoke_campaign"
    run_dir = campaign_dir / "engine_runs" / "run_001"
    raw_dir = run_dir / "raw_outputs" / "mock_smoke" / "DOC-0001"
    raw_dir.mkdir(parents=True)
    for run_index in (2, 3):
        (raw_dir / f"run_{run_index:03d}.json").write_text("{}", encoding="utf-8")

    raw_result = {
        "success": True,
        "full_text": "invoice text",
        "pages": [{"page_number": 1}],
        "tables": [{"table_index": 0}],
        "raw_payload": {
            "runtime_metadata": {
                "engine_generation": "Mock",
                "runtime_class": "MockEngine",
                "package_versions": {},
            }
        },
    }
    status = {
        "status": "COMPLETED",
        "errors": [],
        "results": [
            {
                "config_id": "mock_smoke",
                "document_id": "DOC-0001",
                "run_index": 1,
                "is_warmup": True,
                "status": "SUCCESS",
                "success": True,
                "extract_time_ms": 99,
                "raw_result": raw_result,
            },
            {
                "config_id": "mock_smoke",
                "document_id": "DOC-0001",
                "run_index": 2,
                "is_warmup": False,
                "status": "SUCCESS",
                "success": True,
                "extract_time_ms": 10,
                "resource_summary": {"rss_peak_mb": 50},
                "raw_result": raw_result,
            },
            {
                "config_id": "mock_smoke",
                "document_id": "DOC-0001",
                "run_index": 3,
                "is_warmup": False,
                "status": "SUCCESS",
                "success": True,
                "extract_time_ms": 20,
                "resource_summary": {"rss_peak_mb": 55},
                "raw_result": raw_result,
            },
        ],
    }
    (run_dir / "status.json").write_text(json.dumps(status), encoding="utf-8")
    state = {
        "campaign_id": "smoke_campaign",
        "dataset_fingerprint": "fingerprint",
        "split_path": "benchmark/splits/smoke_test.txt",
        "document_ids": ["DOC-0001"],
        "documents": [
            {
                "document_id": "DOC-0001",
                "filename": "doc.pdf",
                "dataset_category": "sample",
            }
        ],
        "runs": [{"run_id": "run_001", "run_dir": "engine_runs/run_001"}],
        "blockers": [],
    }

    summary = write_campaign_reports(campaign_dir, state)

    assert summary["correctness_artifact_count"] == 1
    assert summary["accuracy_status"] == "NOT_COMPUTED_NO_GROUND_TRUTH"
    correctness_path = campaign_dir / "reports" / "correctness_index.csv"
    with correctness_path.open(encoding="utf-8-sig", newline="") as stream:
        correctness = list(csv.DictReader(stream))
    assert correctness[0]["correctness_run_index"] == "2"
    assert correctness[0]["selection_policy"] == "FIRST_SUCCESSFUL_MEASURED_RUN"

    with (campaign_dir / "reports" / "engine_summary.csv").open(
        encoding="utf-8-sig", newline=""
    ) as stream:
        engine_summary = list(csv.DictReader(stream))
    assert engine_summary[0]["measured_run_count"] == "2"
    assert engine_summary[0]["extract_ms_p50"] == "15.0"
    assert "not computed" in (
        campaign_dir / "reports" / "smoke_report.md"
    ).read_text(encoding="utf-8").lower()
