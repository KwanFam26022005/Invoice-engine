"""Benchmark controller orchestrating isolated engine execution and monitoring."""

import json
import logging
import os
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from document_benchmark.core.contracts import (
    BenchmarkRunSpec,
    DocumentInput,
    EngineSpec,
    RawExtractionResult,
)
from document_benchmark.core.engine_registry import registry
from document_benchmark.core.statuses import EngineStatus
from document_benchmark.runner.environment_probe import probe_environment
from document_benchmark.runner.resource_monitor import ResourceMonitor
from document_benchmark.runner.timeout_manager import terminate_process_tree
from document_benchmark.runner.worker_protocol import WorkerRequest, WorkerResponse
from document_benchmark.storage.run_store import RunStore

logger = logging.getLogger(__name__)


class BenchmarkController:
    """Controller orchestrating benchmark runs across engines and documents."""

    def __init__(self, runs_root: str = "runs") -> None:
        self.run_store = RunStore(runs_root=runs_root)

    def run_benchmark(
        self,
        spec: BenchmarkRunSpec,
        documents: list[DocumentInput],
        progress_callback: Callable[[dict[str, Any]], None] | None = None,
    ) -> dict[str, Any]:
        paths = self.run_store.get_paths(spec.run_id)

        # 1. Save spec & environment probe
        self.run_store.save_run_spec(paths, spec)
        env_data = probe_environment()
        self.run_store.save_environment(paths, env_data)
        self.run_store.save_manifest(paths, documents)

        status_state: dict[str, Any] = {
            "run_id": spec.run_id,
            "status": "RUNNING",
            "started_at": datetime.now(timezone.utc).isoformat(),
            "total_documents": len(documents),
            "total_engine_configs": len(spec.engine_config_ids),
            "completed_tasks": 0,
            "results": [],
            "errors": [],
        }
        self.run_store.save_status(paths, status_state)

        # 2. Iterate through configs and documents
        total_runs_per_doc = spec.warmup_runs + spec.measured_runs

        for config_id in spec.engine_config_ids:
            engine_spec = registry.get_config(config_id)
            if not engine_spec:
                err_msg = f"Engine configuration '{config_id}' not found."
                logger.error(err_msg)
                status_state["errors"].append({"config_id": config_id, "error": err_msg})
                continue

            health = registry.healthcheck_config(config_id)
            if not health.available:
                logger.warning(
                    f"Config '{config_id}' is UNAVAILABLE ({health.error_message}). Skipping."
                )
                status_state["errors"].append(
                    {
                        "config_id": config_id,
                        "status": EngineStatus.UNAVAILABLE.value,
                        "error": health.error_message,
                    }
                )
                continue

            for doc in documents:
                for run_idx in range(1, total_runs_per_doc + 1):
                    is_warmup = run_idx <= spec.warmup_runs

                    if progress_callback:
                        progress_callback(
                            {
                                "config_id": config_id,
                                "document_id": doc.document_id,
                                "filename": doc.filename,
                                "run_index": run_idx,
                                "is_warmup": is_warmup,
                                "status": "RUNNING",
                            }
                        )

                    res_dict = self._execute_isolated_run(
                        spec=spec,
                        engine_spec=engine_spec,
                        doc=doc,
                        run_index=run_idx,
                        is_warmup=is_warmup,
                        paths=paths,
                    )

                    if not is_warmup and res_dict.get("raw_result"):
                        raw_res = RawExtractionResult(**res_dict["raw_result"])
                        self.run_store.save_raw_result(paths, config_id, raw_res)

                    status_state["results"].append(res_dict)
                    status_state["completed_tasks"] += 1
                    self.run_store.save_status(paths, status_state)

        status_state["status"] = "COMPLETED"
        status_state["completed_at"] = datetime.now(timezone.utc).isoformat()
        self.run_store.save_status(paths, status_state)

        return status_state

    def _execute_isolated_run(
        self,
        spec: BenchmarkRunSpec,
        engine_spec: EngineSpec,
        doc: DocumentInput,
        run_index: int,
        is_warmup: bool,
        paths: Any,
    ) -> dict[str, Any]:
        with tempfile.TemporaryDirectory(prefix="bm_worker_") as temp_dir:
            temp_path = Path(temp_dir)
            req_file = temp_path / "request.json"
            resp_file = temp_path / "response.json"
            worker_log_file = paths.engine_log_dir(engine_spec.config_id) / f"{doc.document_id}_run{run_index}.log"

            worker_req = WorkerRequest(
                run_id=spec.run_id,
                engine_spec=engine_spec,
                document=doc,
                action="extract",
                output_file=str(resp_file),
            )

            with open(req_file, "w", encoding="utf-8") as f:
                f.write(worker_req.model_dump_json(indent=2))

            cmd = [
                sys.executable,
                "-m",
                "document_benchmark.runner.isolated_worker",
                "--request-file",
                str(req_file),
            ]

            log_f = open(worker_log_file, "w", encoding="utf-8")

            start_t = time.perf_counter()

            try:
                proc = subprocess.Popen(
                    cmd,
                    stdout=log_f,
                    stderr=subprocess.STDOUT,
                    cwd=os.getcwd(),
                )
            except Exception as e:
                log_f.close()
                return {
                    "config_id": engine_spec.config_id,
                    "document_id": doc.document_id,
                    "run_index": run_index,
                    "is_warmup": is_warmup,
                    "status": EngineStatus.FAILED.value,
                    "error_type": "SubprocessLaunchError",
                    "error_message": str(e),
                    "execution_time_ms": 0.0,
                }

            # Start resource monitor
            monitor = ResourceMonitor(
                target_pid=proc.pid,
                sample_interval_ms=spec.resource_sample_interval_ms,
            )
            monitor.start()

            timed_out = False
            try:
                proc.wait(timeout=float(spec.timeout_seconds))
            except subprocess.TimeoutExpired:
                timed_out = True
                terminate_process_tree(proc.pid)
            finally:
                samples, resource_summary = monitor.stop()
                log_f.close()

            total_ms = (time.perf_counter() - start_t) * 1000.0

            # Save resource samples if measured run
            if not is_warmup:
                self.run_store.save_resource_samples(
                    paths=paths,
                    config_id=engine_spec.config_id,
                    document_id=doc.document_id,
                    run_index=run_index,
                    samples=samples,
                    summary=resource_summary,
                )

            if timed_out:
                return {
                    "config_id": engine_spec.config_id,
                    "document_id": doc.document_id,
                    "run_index": run_index,
                    "is_warmup": is_warmup,
                    "status": EngineStatus.TIMEOUT.value,
                    "error_type": "EngineTimeoutError",
                    "error_message": f"Worker process exceeded timeout of {spec.timeout_seconds}s",
                    "execution_time_ms": total_ms,
                    "resource_summary": resource_summary.model_dump(),
                }

            if not resp_file.exists():
                return {
                    "config_id": engine_spec.config_id,
                    "document_id": doc.document_id,
                    "run_index": run_index,
                    "is_warmup": is_warmup,
                    "status": EngineStatus.FAILED.value,
                    "error_type": "WorkerProtocolError",
                    "error_message": f"Worker process exited with code {proc.returncode} without output response.",
                    "execution_time_ms": total_ms,
                    "resource_summary": resource_summary.model_dump(),
                }

            try:
                with open(resp_file, "r", encoding="utf-8") as f:
                    worker_resp_data = json.load(f)
                worker_resp = WorkerResponse(**worker_resp_data)
            except Exception as e:
                return {
                    "config_id": engine_spec.config_id,
                    "document_id": doc.document_id,
                    "run_index": run_index,
                    "is_warmup": is_warmup,
                    "status": EngineStatus.FAILED.value,
                    "error_type": "WorkerResponseParseError",
                    "error_message": f"Failed to parse worker response JSON: {e}",
                    "execution_time_ms": total_ms,
                    "resource_summary": resource_summary.model_dump(),
                }

            return {
                "config_id": engine_spec.config_id,
                "document_id": doc.document_id,
                "run_index": run_index,
                "is_warmup": is_warmup,
                "status": worker_resp.status.value,
                "success": worker_resp.success,
                "error_type": worker_resp.error_type,
                "error_message": worker_resp.error_message,
                "prepare_time_ms": worker_resp.prepare_time_ms,
                "extract_time_ms": worker_resp.extract_time_ms,
                "total_pipeline_ms": round(total_ms, 2),
                "raw_result": worker_resp.raw_result.model_dump(mode="json") if worker_resp.raw_result else None,
                "resource_summary": resource_summary.model_dump(),
            }
