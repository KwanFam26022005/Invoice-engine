"""Generate non-accuracy smoke benchmark reports from persisted run artifacts."""

from __future__ import annotations

import csv
from datetime import datetime, timezone
import json
from pathlib import Path
import statistics
from typing import Any


def _percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return round(ordered[0], 2)
    position = (len(ordered) - 1) * fraction
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    weight = position - lower
    return round(ordered[lower] * (1 - weight) + ordered[upper] * weight, 2)


def _load_status(run_dir: Path) -> dict[str, Any]:
    status_path = run_dir / "status.json"
    if not status_path.is_file():
        return {
            "status": "MISSING_STATUS",
            "results": [],
            "errors": [{"error": f"Missing status file: {status_path}"}],
        }
    return json.loads(status_path.read_text(encoding="utf-8"))


def _measured_rows(
    campaign_dir: Path,
    state: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    document_metadata = {
        item["document_id"]: item for item in state.get("documents", [])
    }
    rows: list[dict[str, Any]] = []
    blockers: list[dict[str, Any]] = list(state.get("blockers", []))

    for run in state.get("runs", []):
        run_dir = campaign_dir / run["run_dir"]
        status = _load_status(run_dir)
        for error in status.get("errors", []):
            blockers.append(
                {
                    "source": "run_status",
                    "run_id": run.get("run_id"),
                    "config_id": error.get("config_id"),
                    "status": error.get("status"),
                    "reason": error.get("error"),
                }
            )
        for result in status.get("results", []):
            if result.get("is_warmup"):
                continue
            document_id = result.get("document_id", "")
            metadata = document_metadata.get(document_id, {})
            raw = result.get("raw_result") or {}
            raw_payload = raw.get("raw_payload") or {}
            runtime_metadata = raw_payload.get("runtime_metadata") or {}
            resource = result.get("resource_summary") or {}
            rows.append(
                {
                    "campaign_id": state.get("campaign_id"),
                    "run_id": run.get("run_id"),
                    "config_id": result.get("config_id"),
                    "document_id": document_id,
                    "dataset_category": metadata.get("dataset_category"),
                    "filename": metadata.get("filename"),
                    "run_index": result.get("run_index"),
                    "status": result.get("status"),
                    "success": bool(result.get("success")),
                    "error_type": result.get("error_type"),
                    "error_message": result.get("error_message"),
                    "prepare_time_ms": float(result.get("prepare_time_ms") or 0.0),
                    "extract_time_ms": float(result.get("extract_time_ms") or 0.0),
                    "total_pipeline_ms": float(result.get("total_pipeline_ms") or 0.0),
                    "rss_peak_mb": float(resource.get("rss_peak_mb") or 0.0),
                    "uss_peak_mb": float(resource.get("uss_peak_mb") or 0.0),
                    "cpu_peak_percent": float(resource.get("cpu_peak_percent") or 0.0),
                    "gpu_vram_peak_mb": resource.get("gpu_vram_peak_mb"),
                    "text_length": len(raw.get("full_text") or ""),
                    "page_count": len(raw.get("pages") or []),
                    "table_count": len(raw.get("tables") or []),
                    "engine_generation": runtime_metadata.get("engine_generation"),
                    "runtime_class": runtime_metadata.get("runtime_class"),
                    "paddleocr_version": (runtime_metadata.get("package_versions") or {}).get(
                        "paddleocr"
                    ),
                    "paddlepaddle_version": (
                        runtime_metadata.get("package_versions") or {}
                    ).get("paddlepaddle"),
                    "docling_version": (runtime_metadata.get("package_versions") or {}).get(
                        "docling"
                    ),
                    "accuracy_status": "NOT_COMPUTED_NO_GROUND_TRUTH",
                }
            )
    return rows, blockers


def _engine_summary(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        grouped.setdefault(str(row.get("config_id")), []).append(row)

    summary: list[dict[str, Any]] = []
    for config_id, config_rows in sorted(grouped.items()):
        measured = [row for row in config_rows if row.get("status") != "SKIPPED"]
        successful = [row for row in measured if row.get("success")]
        extract_times = [float(row["extract_time_ms"]) for row in successful]
        rss_values = [float(row["rss_peak_mb"]) for row in successful]
        documents = {str(row.get("document_id")) for row in measured}
        successful_documents = {str(row.get("document_id")) for row in successful}
        summary.append(
            {
                "config_id": config_id,
                "document_count": len(documents),
                "successful_document_count": len(successful_documents),
                "measured_run_count": len(measured),
                "successful_run_count": len(successful),
                "failed_run_count": len(measured) - len(successful),
                "skipped_result_count": sum(
                    1 for row in config_rows if row.get("status") == "SKIPPED"
                ),
                "success_rate": round(len(successful) / len(measured), 4) if measured else 0.0,
                "extract_ms_mean": round(statistics.fmean(extract_times), 2)
                if extract_times
                else None,
                "extract_ms_p50": _percentile(extract_times, 0.50),
                "extract_ms_p95": _percentile(extract_times, 0.95),
                "extract_ms_max": round(max(extract_times), 2) if extract_times else None,
                "rss_peak_mb_max": round(max(rss_values), 2) if rss_values else None,
                "text_length_mean": round(
                    statistics.fmean(float(row["text_length"]) for row in successful), 2
                )
                if successful
                else None,
                "table_count_total": sum(int(row["table_count"]) for row in successful),
                "accuracy_status": "NOT_COMPUTED_NO_GROUND_TRUTH",
            }
        )
    return summary


def _correctness_index(
    campaign_dir: Path,
    state: dict[str, Any],
    rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    selected: dict[tuple[str, str], dict[str, Any]] = {}
    run_dirs = {run["run_id"]: run["run_dir"] for run in state.get("runs", [])}
    for row in sorted(rows, key=lambda item: (str(item["config_id"]), str(item["document_id"]), int(item["run_index"] or 0))):
        if not row.get("success"):
            continue
        key = (str(row["config_id"]), str(row["document_id"]))
        if key in selected:
            continue
        relative = (
            Path(run_dirs[str(row["run_id"])])
            / "raw_outputs"
            / str(row["config_id"])
            / str(row["document_id"])
            / f"run_{int(row['run_index']):03d}.json"
        )
        selected[key] = {
            "config_id": row["config_id"],
            "document_id": row["document_id"],
            "run_id": row["run_id"],
            "correctness_run_index": row["run_index"],
            "raw_result_path": relative.as_posix(),
            "path_exists": (campaign_dir / relative).is_file(),
            "selection_policy": "FIRST_SUCCESSFUL_MEASURED_RUN",
            "ground_truth_level": 0,
            "accuracy_status": "NOT_COMPUTED_NO_GROUND_TRUTH",
        }
    return list(selected.values())


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fieldnames: list[str] = []
    for row in rows:
        for key in row:
            if key not in fieldnames:
                fieldnames.append(key)
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _markdown_report(
    state: dict[str, Any],
    summaries: list[dict[str, Any]],
    blockers: list[dict[str, Any]],
    correctness: list[dict[str, Any]],
) -> str:
    lines = [
        f"# Smoke Benchmark Report — {state.get('campaign_id')}",
        "",
        f"- Dataset fingerprint: `{state.get('dataset_fingerprint')}`",
        f"- Split: `{state.get('split_path')}`",
        f"- Documents: {len(state.get('document_ids', []))}",
        f"- Runs recorded: {len(state.get('runs', []))}",
        "- Accuracy: **not computed** because the current smoke documents have ground-truth level 0.",
        "",
        "## Engine summary",
        "",
        "| Config | Documents | Successful runs | Failed runs | Success rate | p50 extract ms | p95 extract ms | Peak RSS MB |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for item in summaries:
        lines.append(
            "| {config_id} | {document_count} | {successful_run_count} | {failed_run_count} | {success_rate:.2%} | {extract_ms_p50} | {extract_ms_p95} | {rss_peak_mb_max} |".format(
                **item
            )
        )
    if not summaries:
        lines.append("| _No measured results_ | 0 | 0 | 0 | 0% | — | — | — |")

    lines.extend(["", "## Correctness artifact policy", ""])
    lines.append(
        "The first successful measured run for each engine/document pair is indexed as the correctness artifact. Other measured repeats remain performance/stability samples and are not counted as additional engines."
    )
    lines.append(f"Indexed correctness artifacts: {len(correctness)}.")

    lines.extend(["", "## Blockers", ""])
    if blockers:
        for blocker in blockers:
            lines.append(
                f"- `{blocker.get('config_id') or blocker.get('source')}`: {blocker.get('reason') or blocker}"
            )
    else:
        lines.append("- None recorded.")
    lines.extend(
        [
            "",
            "## Interpretation boundary",
            "",
            "This report is a smoke/integration benchmark. It may compare availability, execution success, latency, resource usage, text volume, and table output. It must not rank extraction accuracy until reviewed ground truth is available.",
            "",
        ]
    )
    return "\n".join(lines)


def write_campaign_reports(campaign_dir: str | Path, state: dict[str, Any]) -> dict[str, Any]:
    """Regenerate all campaign reports from immutable run directories."""

    root = Path(campaign_dir)
    reports_dir = root / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    rows, blockers = _measured_rows(root, state)
    summaries = _engine_summary(rows)
    correctness = _correctness_index(root, state, rows)

    _write_csv(reports_dir / "document_runs.csv", rows)
    _write_csv(reports_dir / "engine_summary.csv", summaries)
    _write_csv(reports_dir / "correctness_index.csv", correctness)
    (reports_dir / "blockers.json").write_text(
        json.dumps(blockers, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    report = _markdown_report(state, summaries, blockers, correctness)
    (reports_dir / "smoke_report.md").write_text(report, encoding="utf-8")

    campaign_summary = {
        "campaign_id": state.get("campaign_id"),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "dataset_fingerprint": state.get("dataset_fingerprint"),
        "document_count": len(state.get("document_ids", [])),
        "run_count": len(state.get("runs", [])),
        "engine_summary": summaries,
        "blocker_count": len(blockers),
        "correctness_artifact_count": len(correctness),
        "accuracy_status": "NOT_COMPUTED_NO_GROUND_TRUTH",
    }
    (reports_dir / "campaign_summary.json").write_text(
        json.dumps(campaign_summary, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return campaign_summary
