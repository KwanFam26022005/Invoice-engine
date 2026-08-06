"""Data loader for single-document comparison UI."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from document_benchmark.ui.comparison_models import (
    DocumentInfo,
    EngineView,
    PerformanceRepeat,
    PerformanceStats,
)


def validate_path_containment(base_dir: Path, target_path: Path) -> Path:
    """Ensure target_path resolves strictly within base_dir to prevent path traversal."""
    resolved_base = base_dir.resolve()
    resolved_target = target_path.resolve()
    try:
        resolved_target.relative_to(resolved_base)
    except ValueError as exc:
        raise ValueError(
            f"Path containment violation: '{target_path}' is outside base directory '{base_dir}'"
        ) from exc
    return resolved_target


def load_campaign_json(campaign_dir: Path) -> dict[str, Any]:
    """Load and validate campaign.json."""
    campaign_file = campaign_dir / "campaign.json"
    if not campaign_file.exists():
        raise FileNotFoundError(f"Campaign manifest missing: {campaign_file}")
    return json.loads(campaign_file.read_text(encoding="utf-8"))


def load_correctness_index(campaign_dir: Path) -> list[dict[str, str]]:
    """Load correctness_index.csv mapping (config_id, document_id) -> raw_result_path."""
    ci_path = campaign_dir / "reports" / "correctness_index.csv"
    if not ci_path.exists():
        return []
    with ci_path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def load_document_runs_csv(campaign_dir: Path) -> list[dict[str, str]]:
    """Load document_runs.csv containing measured repeat metrics."""
    dr_path = campaign_dir / "reports" / "document_runs.csv"
    if not dr_path.exists():
        return []
    with dr_path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def load_engine_summary_csv(campaign_dir: Path) -> list[dict[str, str]]:
    """Load engine_summary.csv containing campaign-level aggregate stats."""
    es_path = campaign_dir / "reports" / "engine_summary.csv"
    if not es_path.exists():
        return []
    with es_path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def resolve_pdf_path(dataset_root: Path, benchmark_path: str) -> tuple[Path | None, bool, str | None]:
    """Resolve PDF file path with strict path containment verification."""
    if not benchmark_path:
        return None, False, "No benchmark path specified."
    try:
        target_path = dataset_root / benchmark_path
        resolved_path = validate_path_containment(dataset_root, target_path)
        if not resolved_path.exists():
            return resolved_path, False, f"PDF file not found at: {resolved_path}"
        return resolved_path, True, None
    except Exception as exc:
        return None, False, str(exc)


def load_document_info(
    dataset_root: Path,
    campaign_json: dict[str, Any],
    document_id: str,
) -> DocumentInfo:
    """Extract DocumentInfo for a specific document_id from campaign manifest."""
    doc_entries = campaign_json.get("documents", [])
    doc_entry = next((d for d in doc_entries if d.get("document_id") == document_id), None)

    if not doc_entry:
        return DocumentInfo(
            document_id=document_id,
            filename=f"{document_id}.pdf",
            pdf_available=False,
            pdf_error=f"Document ID '{document_id}' not found in campaign.json",
        )

    b_path = doc_entry.get("benchmark_path", "")
    pdf_path, is_avail, pdf_err = resolve_pdf_path(dataset_root, b_path)

    return DocumentInfo(
        document_id=document_id,
        filename=doc_entry.get("filename", f"{document_id}.pdf"),
        category=doc_entry.get("metadata", {}).get("dataset_category", "unknown"),
        page_count=int(doc_entry.get("page_count", 1)),
        sha256=doc_entry.get("sha256", ""),
        input_profile=doc_entry.get("metadata", {}).get("input_profile", "scan_ocr"),
        ground_truth_level=int(doc_entry.get("metadata", {}).get("ground_truth_level", 0)),
        benchmark_path=b_path,
        resolved_pdf_path=str(pdf_path) if pdf_path else None,
        pdf_available=is_avail,
        pdf_error=pdf_err,
    )


def read_log_tail(log_path: Path, max_lines: int = 200) -> list[str]:
    """Read tail lines from a log file safely."""
    if not log_path.exists():
        return []
    try:
        lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
        return lines[-max_lines:]
    except Exception:
        return []


def load_engine_view_for_document(
    campaign_dir: Path,
    campaign_json: dict[str, Any],
    correctness_rows: list[dict[str, str]],
    document_runs_rows: list[dict[str, str]],
    config_id: str,
    document_id: str,
) -> EngineView | None:
    """Load EngineView for a given (config_id, document_id) pairing."""
    c_row = next(
        (r for r in correctness_rows if r.get("config_id") == config_id and r.get("document_id") == document_id),
        None,
    )
    if not c_row:
        return None

    rel_raw_path = c_row.get("raw_result_path", "")
    if not rel_raw_path:
        return None

    # Validate path containment for raw result
    try:
        raw_full_path = validate_path_containment(campaign_dir, campaign_dir / rel_raw_path)
    except ValueError:
        return None

    if not raw_full_path.exists():
        return None

    raw_bytes = raw_full_path.read_bytes()
    raw_size_bytes = len(raw_bytes)

    try:
        raw_data = json.loads(raw_bytes.decode("utf-8"))
    except Exception:
        return None

    # Identify run_id and run_dir
    runs = campaign_json.get("runs", [])
    run_entry = next((r for r in runs if config_id in r.get("engine_config_ids", [])), None)
    run_id = run_entry.get("run_id", "unknown") if run_entry else "unknown"
    run_dir_rel = run_entry.get("run_dir", "") if run_entry else ""

    # Load environment.json if available
    env_data: dict[str, Any] = {}
    if run_dir_rel:
        try:
            env_file = validate_path_containment(campaign_dir, campaign_dir / run_dir_rel / "environment.json")
            if env_file.exists():
                env_data = json.loads(env_file.read_text(encoding="utf-8"))
        except Exception:
            pass

    # Extract log tail
    logs_tail: list[str] = []
    if run_dir_rel:
        try:
            logs_dir = validate_path_containment(campaign_dir, campaign_dir / run_dir_rel / "logs")
            log_files = list(logs_dir.glob("*.log"))
            if log_files:
                logs_tail = read_log_tail(log_files[0])
        except Exception:
            pass

    full_text = raw_data.get("full_text", "") or ""
    field_cands = raw_data.get("field_candidates", {}) or {}
    pages = raw_data.get("pages", []) or []
    tables = raw_data.get("tables", []) or []

    # Read runtime metadata
    payload = raw_data.get("raw_payload", {}) or {}
    rt_meta = payload.get("runtime_metadata", {}) or {}

    pkg_env = env_data.get("python", {}).get("packages", {}) or {}
    pkg_rt = rt_meta.get("package_versions", {}) or {}

    # Check provenance mismatch
    provenance_warnings: list[str] = []
    provenance_mismatch = False
    for pkg_name, rt_ver in pkg_rt.items():
        env_ver = pkg_env.get(pkg_name)
        if rt_ver != env_ver:
            provenance_mismatch = True
            provenance_warnings.append(
                f"Version mismatch for '{pkg_name}': environment.json={env_ver}, runtime_metadata={rt_ver}"
            )

    # Performance repeats for this doc & config from document_runs.csv
    doc_runs = [
        r for r in document_runs_rows
        if r.get("config_id") == config_id and r.get("document_id") == document_id
    ]

    performance_repeats: list[PerformanceRepeat] = []
    for dr in doc_runs:
        performance_repeats.append(
            PerformanceRepeat(
                run_index=int(dr.get("run_index", 0)),
                success=dr.get("status", "").upper() == "SUCCESS",
                extract_time_ms=float(dr.get("extract_time_ms", 0.0) or 0.0),
                total_pipeline_ms=float(dr.get("total_pipeline_ms", 0.0) or 0.0),
                rss_peak_mb=float(dr.get("rss_peak_mb", 0.0)) if dr.get("rss_peak_mb") else None,
                uss_peak_mb=float(dr.get("uss_peak_mb", 0.0)) if dr.get("uss_peak_mb") else None,
                cpu_peak_percent=float(dr.get("cpu_peak_percent", 0.0)) if dr.get("cpu_peak_percent") else None,
                status=dr.get("status", "SUCCESS"),
                error_type=dr.get("error_type"),
                error_message=dr.get("error_message"),
            )
        )

    # Compute performance stats
    perf_stats = PerformanceStats()
    if performance_repeats:
        succ_repeats = [r for r in performance_repeats if r.success]
        extract_times = [r.extract_time_ms for r in succ_repeats]
        total_times = [r.total_pipeline_ms for r in succ_repeats]
        rss_peaks = [r.rss_peak_mb for r in succ_repeats if r.rss_peak_mb is not None]
        uss_peaks = [r.uss_peak_mb for r in succ_repeats if r.uss_peak_mb is not None]
        cpu_peaks = [r.cpu_peak_percent for r in succ_repeats if r.cpu_peak_percent is not None]

        perf_stats.measured_count = len(performance_repeats)
        perf_stats.successful_count = len(succ_repeats)
        perf_stats.failed_count = len(performance_repeats) - len(succ_repeats)

        if extract_times:
            sorted_ext = sorted(extract_times)
            n = len(sorted_ext)
            perf_stats.extract_ms_mean = round(sum(sorted_ext) / n, 2)
            perf_stats.extract_ms_min = round(sorted_ext[0], 2)
            perf_stats.extract_ms_max = round(sorted_ext[-1], 2)
            perf_stats.extract_ms_median = round(sorted_ext[n // 2], 2)
            perf_stats.extract_ms_p50 = perf_stats.extract_ms_median
            p95_idx = max(0, int(0.95 * n) - 1)
            perf_stats.extract_ms_p95 = round(sorted_ext[p95_idx], 2)

            if n > 1:
                variance = sum((x - perf_stats.extract_ms_mean) ** 2 for x in sorted_ext) / (n - 1)
                perf_stats.extract_ms_std = round(variance ** 0.5, 2)
                if perf_stats.extract_ms_mean > 0:
                    perf_stats.extract_ms_cv = round(perf_stats.extract_ms_std / perf_stats.extract_ms_mean, 4)

        if total_times:
            perf_stats.total_pipeline_ms_mean = round(sum(total_times) / len(total_times), 2)
        if rss_peaks:
            perf_stats.rss_peak_mb_max = round(max(rss_peaks), 2)
        if uss_peaks:
            perf_stats.uss_peak_mb_max = round(max(uss_peaks), 2)
        if cpu_peaks:
            perf_stats.cpu_peak_percent_max = round(max(cpu_peaks), 2)
            if all(c == 0.0 for c in cpu_peaks):
                perf_stats.cpu_metrics_valid = False
                perf_stats.cpu_metrics_warning = "CPU peak percent is 0.0 across all samples (possible metric collection issue)."

    # Read prepare time from run status.json
    if run_dir_rel:
        try:
            status_file = validate_path_containment(campaign_dir, campaign_dir / run_dir_rel / "status.json")
            if status_file.exists():
                st_data = json.loads(status_file.read_text(encoding="utf-8"))
                for r_item in st_data.get("results", []):
                    if r_item.get("document_id") == document_id and r_item.get("prepare_time_ms"):
                        perf_stats.prepare_time_ms = round(float(r_item["prepare_time_ms"]), 2)
                        break
        except Exception:
            pass

    return EngineView(
        config_id=config_id,
        engine_name="Docling OCR" if "docling" in config_id else "PP-StructureV3",
        run_id=run_id,
        run_dir=run_dir_rel,
        success=bool(raw_data.get("success", True)),
        correctness_run_index=int(c_row.get("run_index", 2)),
        raw_result_path=rel_raw_path,
        raw_json_size_bytes=raw_size_bytes,
        full_text=full_text,
        char_count=len(full_text),
        word_count=len(full_text.split()),
        line_count=len(full_text.splitlines()),
        page_count=len(pages) or 1,
        table_count=len(tables),
        field_candidates=field_cands,
        warnings=raw_data.get("warnings", []) or [],
        errors=[raw_data["error_message"]] if raw_data.get("error_message") else [],
        runtime_class=rt_meta.get("runtime_class", "N/A"),
        engine_generation=rt_meta.get("engine_generation", "N/A"),
        benchmark_track=rt_meta.get("benchmark_track", "N/A"),
        ocr_enabled=bool(rt_meta.get("ocr_enabled", False)),
        ocr_engine=rt_meta.get("ocr_engine"),
        ocr_languages=rt_meta.get("ocr_languages", []) or [],
        package_versions_runtime=pkg_rt,
        package_versions_env=pkg_env,
        provenance_mismatch=provenance_mismatch,
        provenance_warnings=provenance_warnings,
        performance_repeats=performance_repeats,
        performance_stats=perf_stats,
        logs_tail=logs_tail,
        raw_payload=payload,
    )
