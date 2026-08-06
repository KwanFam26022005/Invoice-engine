"""End-to-end smoke campaign test using the isolated MockEngine worker."""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

from document_benchmark.smoke.runner import run_smoke_campaign


def test_smoke_campaign_runs_mock_and_generates_reports(tmp_path: Path) -> None:
    dataset_root = tmp_path / "dataset"
    pdf_dir = dataset_root / "benchmark" / "documents" / "sample"
    manifest_dir = dataset_root / "benchmark" / "manifests"
    split_dir = dataset_root / "benchmark" / "splits"
    pdf_dir.mkdir(parents=True)
    manifest_dir.mkdir(parents=True)
    split_dir.mkdir(parents=True)

    pdf_path = pdf_dir / "sample.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\nsmoke mock fixture\n%%EOF\n")
    sha256 = hashlib.sha256(pdf_path.read_bytes()).hexdigest()
    manifest_fields = [
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
    with (manifest_dir / "documents.csv").open(
        "w", encoding="utf-8", newline=""
    ) as stream:
        writer = csv.DictWriter(stream, fieldnames=manifest_fields)
        writer.writeheader()
        writer.writerow(
            {
                "document_id": "DOC-SMOKE-001",
                "dataset_category": "sample",
                "document_family": "INVOICE",
                "source_group": "TEST",
                "benchmark_filename": pdf_path.name,
                "benchmark_path": "benchmark/documents/sample/sample.pdf",
                "sha256": sha256,
                "page_count": 1,
                "has_text_layer": False,
                "text_character_count": 0,
                "is_image_only_pdf": True,
                "is_merged": False,
                "include_in_benchmark": True,
                "quality_status": "VALID",
                "ground_truth_level": 0,
            }
        )
    (split_dir / "smoke_test.txt").write_text("DOC-SMOKE-001\n", encoding="utf-8")

    configs_dir = tmp_path / "configs"
    configs_dir.mkdir()
    (configs_dir / "mock_smoke.yaml").write_text(
        (
            "engine_id: mock\n"
            "engine_version: 1.0.0\n"
            "config_id: mock_smoke_campaign\n"
            "output_kind: document_ir\n"
            "supports_pdf_text: true\n"
            "supports_scanned_pdf: true\n"
            "supports_tables: true\n"
            "enabled: true\n"
            "device: cpu\n"
            "options:\n"
            "  benchmark_track: scan_ocr\n"
            "  prepare_delay_ms: 1\n"
            "  extract_delay_ms: 1\n"
            "  mock_family: invoice\n"
        ),
        encoding="utf-8",
    )

    exit_code, summary = run_smoke_campaign(
        dataset_root=dataset_root,
        configs_dir=configs_dir,
        engine_config_ids=["mock_smoke_campaign"],
        campaign_root=tmp_path / "campaigns",
        campaign_id="smoke_e2e",
        expected_count=1,
        warmup_runs=0,
        measured_runs=1,
        timeout_seconds=30,
    )

    assert exit_code == 0
    assert summary["run_count"] == 1
    assert summary["correctness_artifact_count"] == 1
    campaign_dir = tmp_path / "campaigns" / "smoke_e2e"
    state = json.loads((campaign_dir / "campaign.json").read_text(encoding="utf-8"))
    assert state["document_ids"] == ["DOC-SMOKE-001"]
    assert state["accuracy_status"] == "NOT_COMPUTED_NO_GROUND_TRUTH"
    assert (campaign_dir / "reports" / "document_runs.csv").exists()
    assert (campaign_dir / "reports" / "engine_summary.csv").exists()
    assert (campaign_dir / "reports" / "correctness_index.csv").exists()
    assert not (campaign_dir / ".campaign.lock").exists()
