"""CLI and orchestration for reproducible 10-document smoke campaigns."""

from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
from typing import Any, Iterator

from document_benchmark.core.contracts import BenchmarkRunSpec
from document_benchmark.core.engine_registry import registry
from document_benchmark.runner.benchmark_controller import BenchmarkController
from document_benchmark.smoke.dataset import SmokeDataset, SmokeDatasetError, load_smoke_dataset
from document_benchmark.smoke.preflight import EnginePreflightResult, run_engine_preflight
from document_benchmark.smoke.report import write_campaign_reports

_CAMPAIGN_SCHEMA_VERSION = 1


def _utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def _atomic_write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(data, indent=2, ensure_ascii=False, default=str), encoding="utf-8"
    )
    temporary.replace(path)


@contextmanager
def _campaign_lock(campaign_dir: Path) -> Iterator[None]:
    campaign_dir.mkdir(parents=True, exist_ok=True)
    lock_path = campaign_dir / ".campaign.lock"
    try:
        descriptor = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as exc:
        raise RuntimeError(
            f"Campaign is already locked by another process: {lock_path}"
        ) from exc
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(f"pid={os.getpid()}\n")
        yield
    finally:
        lock_path.unlink(missing_ok=True)


def load_engine_configs(configs_dir: str | Path) -> None:
    """Register all YAML profiles from a deterministic config directory."""

    root = Path(configs_dir)
    if not root.is_dir():
        raise FileNotFoundError(f"Engine config directory not found: {root}")
    for config_path in sorted(root.glob("*.yaml")):
        registry.load_config_from_file(str(config_path))


def _document_snapshot(dataset: SmokeDataset) -> list[dict[str, Any]]:
    return [
        {
            "document_id": document.document_id,
            "filename": document.filename,
            "sha256": document.sha256,
            "page_count": document.page_count,
            "dataset_category": document.metadata.get("dataset_category"),
            "input_profile": document.metadata.get("input_profile"),
            "ground_truth_level": document.metadata.get("ground_truth_level", 0),
            "benchmark_path": document.metadata.get("benchmark_path"),
        }
        for document in dataset.documents
    ]


def _new_campaign_state(
    campaign_id: str,
    campaign_dir: Path,
    dataset: SmokeDataset,
) -> dict[str, Any]:
    now = datetime.now(timezone.utc).isoformat()
    return {
        "schema_version": _CAMPAIGN_SCHEMA_VERSION,
        "campaign_id": campaign_id,
        "campaign_dir": str(campaign_dir.resolve()),
        "dataset_root": str(dataset.dataset_root),
        "manifest_path": str(dataset.manifest_path.relative_to(dataset.dataset_root)),
        "split_path": str(dataset.split_path.relative_to(dataset.dataset_root)),
        "dataset_fingerprint": dataset.fingerprint,
        "document_ids": dataset.document_ids,
        "documents": _document_snapshot(dataset),
        "created_at": now,
        "updated_at": now,
        "runs": [],
        "preflight_history": [],
        "blockers": [],
        "accuracy_status": "NOT_COMPUTED_NO_GROUND_TRUTH",
    }


def _load_or_create_state(
    campaign_id: str,
    campaign_dir: Path,
    dataset: SmokeDataset,
) -> dict[str, Any]:
    state_path = campaign_dir / "campaign.json"
    if not state_path.exists():
        return _new_campaign_state(campaign_id, campaign_dir, dataset)
    state = json.loads(state_path.read_text(encoding="utf-8"))
    if state.get("schema_version") != _CAMPAIGN_SCHEMA_VERSION:
        raise RuntimeError("Unsupported smoke campaign schema version")
    if state.get("campaign_id") != campaign_id:
        raise RuntimeError("Campaign ID does not match existing campaign state")
    if state.get("dataset_fingerprint") != dataset.fingerprint:
        raise RuntimeError(
            "Dataset fingerprint differs from the existing campaign; use a new campaign ID"
        )
    if state.get("document_ids") != dataset.document_ids:
        raise RuntimeError(
            "Smoke split order differs from the existing campaign; use a new campaign ID"
        )
    return state


def _preflight_snapshot(results: list[EnginePreflightResult]) -> dict[str, Any]:
    return {
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "python_executable": sys.executable,
        "results": [result.model_dump(mode="json") for result in results],
    }


def _record_blockers(
    state: dict[str, Any],
    results: list[EnginePreflightResult],
) -> None:
    known = {
        (item.get("source"), item.get("config_id"), item.get("reason"))
        for item in state.get("blockers", [])
    }
    for result in results:
        if result.ready:
            continue
        reason = "; ".join(result.reasons) or "Engine preflight failed"
        key = ("preflight", result.config_id, reason)
        if key in known:
            continue
        state.setdefault("blockers", []).append(
            {
                "source": "preflight",
                "config_id": result.config_id,
                "status": result.health_status,
                "reason": reason,
                "checked_at": result.checked_at,
                "python_executable": result.python_executable,
            }
        )
        known.add(key)


def run_smoke_campaign(
    *,
    dataset_root: str | Path,
    configs_dir: str | Path,
    engine_config_ids: list[str],
    campaign_root: str | Path = "runs/smoke",
    campaign_id: str | None = None,
    split_path: str | Path = "benchmark/splits/smoke_test.txt",
    manifest_path: str | Path = "benchmark/manifests/documents.csv",
    expected_count: int | None = 10,
    expected_profile: str | None = "scan_ocr",
    warmup_runs: int = 1,
    measured_runs: int = 3,
    timeout_seconds: int = 600,
    resource_sample_interval_ms: int = 200,
    preflight_only: bool = False,
    report_only: bool = False,
    allow_unavailable: bool = False,
) -> tuple[int, dict[str, Any]]:
    """Run or extend a campaign, returning a process-style exit code and summary."""

    if not engine_config_ids and not report_only:
        raise ValueError("At least one engine config ID is required")
    if warmup_runs < 0 or measured_runs < 1:
        raise ValueError("warmup_runs must be >= 0 and measured_runs must be >= 1")

    dataset = load_smoke_dataset(
        dataset_root,
        split_path=split_path,
        manifest_path=manifest_path,
        expected_count=expected_count,
        expected_profile=expected_profile,
    )
    resolved_campaign_id = campaign_id or f"smoke_{_utc_stamp()}"
    campaign_dir = Path(campaign_root).resolve() / resolved_campaign_id

    with _campaign_lock(campaign_dir):
        state = _load_or_create_state(resolved_campaign_id, campaign_dir, dataset)
        if report_only:
            state["updated_at"] = datetime.now(timezone.utc).isoformat()
            _atomic_write_json(campaign_dir / "campaign.json", state)
            summary = write_campaign_reports(campaign_dir, state)
            return 0, summary

        load_engine_configs(configs_dir)
        preflight_results = [
            run_engine_preflight(config_id) for config_id in engine_config_ids
        ]
        snapshot = _preflight_snapshot(preflight_results)
        state.setdefault("preflight_history", []).append(snapshot)
        _record_blockers(state, preflight_results)
        preflight_path = campaign_dir / "preflight" / f"preflight_{_utc_stamp()}.json"
        _atomic_write_json(preflight_path, snapshot)
        state["updated_at"] = datetime.now(timezone.utc).isoformat()
        _atomic_write_json(campaign_dir / "campaign.json", state)

        ready_configs = [result.config_id for result in preflight_results if result.ready]
        unavailable = [result for result in preflight_results if not result.ready]
        if preflight_only:
            summary = write_campaign_reports(campaign_dir, state)
            return (0 if not unavailable else 2), summary
        if unavailable and not allow_unavailable:
            summary = write_campaign_reports(campaign_dir, state)
            return 2, summary
        if not ready_configs:
            summary = write_campaign_reports(campaign_dir, state)
            return 2, summary

        run_id = f"{resolved_campaign_id}_{_utc_stamp()}"
        engine_runs_root = campaign_dir / "engine_runs"
        run_spec = BenchmarkRunSpec(
            run_id=run_id,
            document_ids=dataset.document_ids,
            engine_config_ids=ready_configs,
            timeout_seconds=timeout_seconds,
            warmup_runs=warmup_runs,
            measured_runs=measured_runs,
            resource_sample_interval_ms=resource_sample_interval_ms,
        )

        def on_progress(progress: dict[str, Any]) -> None:
            print(
                "Smoke progress: "
                f"config={progress.get('config_id')} "
                f"document={progress.get('document_id')} "
                f"run={progress.get('run_index')} "
                f"status={progress.get('status')}"
            )

        status = BenchmarkController(runs_root=str(engine_runs_root)).run_benchmark(
            spec=run_spec,
            documents=dataset.documents,
            progress_callback=on_progress,
        )
        relative_run_dir = (Path("engine_runs") / run_id).as_posix()
        state.setdefault("runs", []).append(
            {
                "run_id": run_id,
                "run_dir": relative_run_dir,
                "engine_config_ids": ready_configs,
                "python_executable": sys.executable,
                "started_at": status.get("started_at"),
                "completed_at": status.get("completed_at"),
                "status": status.get("status"),
                "successful_measured_runs": status.get("successful_measured_runs", 0),
                "failed_measured_runs": status.get("failed_measured_runs", 0),
                "skipped_tasks": status.get("skipped_tasks", 0),
            }
        )
        state["updated_at"] = datetime.now(timezone.utc).isoformat()
        _atomic_write_json(campaign_dir / "campaign.json", state)
        summary = write_campaign_reports(campaign_dir, state)
        exit_code = 0 if status.get("status") == "COMPLETED" else 1
        return exit_code, summary


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run or extend a reproducible document-engine smoke benchmark campaign"
    )
    parser.add_argument("--dataset-root", required=True)
    parser.add_argument("--configs-dir", default="configs/engines")
    parser.add_argument("--engines", nargs="*", default=[])
    parser.add_argument("--campaign-root", default="runs/smoke")
    parser.add_argument("--campaign-id")
    parser.add_argument("--split", default="benchmark/splits/smoke_test.txt")
    parser.add_argument("--manifest", default="benchmark/manifests/documents.csv")
    parser.add_argument("--expected-count", type=int, default=10)
    parser.add_argument("--expected-profile", default="scan_ocr")
    parser.add_argument("--warmup-runs", type=int, default=1)
    parser.add_argument("--measured-runs", type=int, default=3)
    parser.add_argument("--timeout", type=int, default=600)
    parser.add_argument("--resource-sample-interval-ms", type=int, default=200)
    parser.add_argument("--preflight-only", action="store_true")
    parser.add_argument("--report-only", action="store_true")
    parser.add_argument("--allow-unavailable", action="store_true")
    parser.add_argument("--no-count-check", action="store_true")
    parser.add_argument("--allow-mixed-profile", action="store_true")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    try:
        exit_code, summary = run_smoke_campaign(
            dataset_root=args.dataset_root,
            configs_dir=args.configs_dir,
            engine_config_ids=args.engines,
            campaign_root=args.campaign_root,
            campaign_id=args.campaign_id,
            split_path=args.split,
            manifest_path=args.manifest,
            expected_count=None if args.no_count_check else args.expected_count,
            expected_profile=None if args.allow_mixed_profile else args.expected_profile,
            warmup_runs=args.warmup_runs,
            measured_runs=args.measured_runs,
            timeout_seconds=args.timeout,
            resource_sample_interval_ms=args.resource_sample_interval_ms,
            preflight_only=args.preflight_only,
            report_only=args.report_only,
            allow_unavailable=args.allow_unavailable,
        )
    except (SmokeDatasetError, FileNotFoundError, RuntimeError, ValueError) as exc:
        sys.stderr.write(f"Smoke benchmark failed before execution: {exc}\n")
        raise SystemExit(2) from exc
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    raise SystemExit(exit_code)


if __name__ == "__main__":
    main()
