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
from document_benchmark.runner.input_compatibility import assess_input_compatibility
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
        self.run_store.save_run_spec(paths, spec)
        self.run_store.save_environment(paths, probe_environment())
        self.run_store.save_manifest(paths, documents)

        status_state: dict[str, Any] = {
            "run_id": spec.run_id,
            "status": "RUNNING",
            "started_at": datetime.now(timezone.utc).isoformat(),
            "total_documents": len(documents),
            "total_engine_configs": len(spec.engine_config_ids),
            "completed_tasks": 0,
            "skipped_tasks": 0,
            "results": [],
            "errors": [],
        }
        self.run_store.save_status(paths, status_state)

        for config_id in spec.engine_config_ids:
            engine_spec = registry.get_config(config_id)
            if engine_spec is None:
                message = f"Engine configuration '{config_id}' not found."
                status_state["errors"].append(
                    {
                        "config_id": config_id,
                        "status": EngineStatus.UNAVAILABLE.value,
                        "error": message,
                    }
                )
                continue

            health = registry.healthcheck_config(config_id)
            if not health.available:
                status_state["errors"].append(
                    {
                        "config_id": config_id,
                        "status": EngineStatus.UNAVAILABLE.value,
                        "error": health.error_message,
                        "runtime_metadata": health.runtime_metadata,
                    }
                )
                continue

            for document in documents:
                compatibility = assess_input_compatibility(engine_spec, document)
                if not compatibility.supported:
                    skipped_result = {
                        "config_id": config_id,
                        "document_id": document.document_id,
                        "run_index": 0,
                        "is_warmup": False,
                        "status": EngineStatus.SKIPPED.value,
                        "success": False,
                        "error_type": "UnsupportedBenchmarkInput",
                        "error_message": compatibility.reason,
                        "input_profile": compatibility.input_profile,
                        "engine_track": compatibility.engine_track,
                        "prepare_time_ms": 0.0,
                        "extract_time_ms": 0.0,
                        "total_pipeline_ms": 0.0,
                        "raw_result": None,
                        "resource_summary": {},
                        "exit_code": None,
                    }
                    status_state["results"].append(skipped_result)
                    status_state["completed_tasks"] += 1
                    status_state["skipped_tasks"] += 1
                    if progress_callback:
                        progress_callback(
                            {
                                "config_id": config_id,
                                "document_id": document.document_id,
                                "filename": document.filename,
                                "run_index": 0,
                                "is_warmup": False,
                                "status": EngineStatus.SKIPPED.value,
                                "message": compatibility.reason,
                            }
                        )
                    self.run_store.save_status(paths, status_state)
                    continue

                if progress_callback:
                    progress_callback(
                        {
                            "config_id": config_id,
                            "document_id": document.document_id,
                            "filename": document.filename,
                            "run_index": 0,
                            "is_warmup": False,
                            "status": EngineStatus.PREPARING.value,
                        }
                    )

                batch_result = self._execute_isolated_batch(
                    spec=spec,
                    engine_spec=engine_spec,
                    document=document,
                    paths=paths,
                )

                run_results = batch_result.pop("run_results", [])
                if not run_results:
                    status_state["results"].append(batch_result)
                    status_state["completed_tasks"] += 1
                else:
                    for run_result in run_results:
                        combined = {
                            "config_id": config_id,
                            "document_id": document.document_id,
                            "run_index": run_result["run_index"],
                            "is_warmup": run_result["is_warmup"],
                            "status": run_result["status"],
                            "success": run_result["success"],
                            "error_type": run_result.get("error_type"),
                            "error_message": run_result.get("error_message"),
                            "prepare_time_ms": (
                                batch_result["prepare_time_ms"]
                                if run_result["run_index"] == 1
                                else 0.0
                            ),
                            "extract_time_ms": run_result.get("extract_time_ms", 0.0),
                            "total_pipeline_ms": batch_result["total_pipeline_ms"],
                            "raw_result": run_result.get("raw_result"),
                            "resource_summary": batch_result["resource_summary"],
                            "exit_code": batch_result.get("exit_code"),
                        }
                        status_state["results"].append(combined)
                        status_state["completed_tasks"] += 1

                        if not run_result["is_warmup"] and run_result.get("raw_result"):
                            raw_result = RawExtractionResult(**run_result["raw_result"])
                            self.run_store.save_raw_result(
                                paths,
                                config_id,
                                raw_result,
                                run_index=run_result["run_index"],
                            )

                        if progress_callback:
                            progress_callback(
                                {
                                    "config_id": config_id,
                                    "document_id": document.document_id,
                                    "filename": document.filename,
                                    "run_index": run_result["run_index"],
                                    "is_warmup": run_result["is_warmup"],
                                    "status": run_result["status"],
                                }
                            )

                self.run_store.save_status(paths, status_state)

        measured_results = [
            result
            for result in status_state["results"]
            if not result.get("is_warmup", False)
            and result.get("status") != EngineStatus.SKIPPED.value
        ]
        successful_results = [result for result in measured_results if result.get("success")]
        failed_results = [result for result in measured_results if not result.get("success")]

        if (
            measured_results
            and len(successful_results) == len(measured_results)
            and not status_state["errors"]
            and status_state["skipped_tasks"] == 0
        ):
            final_status = "COMPLETED"
        elif successful_results:
            final_status = "COMPLETED_WITH_ERRORS"
        else:
            final_status = "FAILED"

        status_state["status"] = final_status
        status_state["successful_measured_runs"] = len(successful_results)
        status_state["failed_measured_runs"] = len(failed_results)
        status_state["completed_at"] = datetime.now(timezone.utc).isoformat()
        self.run_store.save_status(paths, status_state)
        return status_state

    def _execute_isolated_batch(
        self,
        spec: BenchmarkRunSpec,
        engine_spec: EngineSpec,
        document: DocumentInput,
        paths: Any,
    ) -> dict[str, Any]:
        with tempfile.TemporaryDirectory(prefix="bm_worker_") as temp_dir:
            temp_path = Path(temp_dir)
            request_file = temp_path / "request.json"
            response_file = temp_path / "response.json"
            worker_log_file = (
                paths.engine_log_dir(engine_spec.config_id) / f"{document.document_id}_batch.log"
            )

            worker_request = WorkerRequest(
                run_id=spec.run_id,
                engine_spec=engine_spec,
                document=document,
                action="benchmark",
                output_file=str(response_file),
                warmup_runs=spec.warmup_runs,
                measured_runs=spec.measured_runs,
                reuse_prepared_engine=True,
            )
            request_file.write_text(worker_request.model_dump_json(indent=2), encoding="utf-8")

            command = [
                sys.executable,
                "-m",
                "document_benchmark.runner.isolated_worker",
                "--request-file",
                str(request_file),
            ]

            started = time.perf_counter()
            with worker_log_file.open("w", encoding="utf-8") as log_file:
                try:
                    process = subprocess.Popen(
                        command,
                        stdout=log_file,
                        stderr=subprocess.STDOUT,
                        cwd=os.getcwd(),
                    )
                except Exception as exc:
                    return self._failed_batch(
                        engine_spec,
                        document,
                        "SubprocessLaunchError",
                        str(exc),
                    )

                monitor = ResourceMonitor(
                    target_pid=process.pid,
                    sample_interval_ms=spec.resource_sample_interval_ms,
                )
                monitor.start()
                timed_out = False
                try:
                    process.wait(timeout=float(spec.timeout_seconds))
                except subprocess.TimeoutExpired:
                    timed_out = True
                    terminate_process_tree(process.pid)
                finally:
                    samples, resource_summary = monitor.stop()

            total_ms = round((time.perf_counter() - started) * 1000.0, 2)
            self.run_store.save_resource_samples(
                paths=paths,
                config_id=engine_spec.config_id,
                document_id=document.document_id,
                run_index=0,
                samples=samples,
                summary=resource_summary,
            )

            if timed_out:
                return {
                    **self._failed_batch(
                        engine_spec,
                        document,
                        "EngineTimeoutError",
                        f"Worker process exceeded timeout of {spec.timeout_seconds}s",
                    ),
                    "status": EngineStatus.TIMEOUT.value,
                    "total_pipeline_ms": total_ms,
                    "resource_summary": resource_summary.model_dump(),
                    "exit_code": process.returncode,
                }

            if not response_file.exists():
                return {
                    **self._failed_batch(
                        engine_spec,
                        document,
                        "WorkerProtocolError",
                        f"Worker exited with code {process.returncode} without a response file",
                    ),
                    "total_pipeline_ms": total_ms,
                    "resource_summary": resource_summary.model_dump(),
                    "exit_code": process.returncode,
                }

            try:
                response = WorkerResponse(
                    **json.loads(response_file.read_text(encoding="utf-8"))
                )
            except Exception as exc:
                return {
                    **self._failed_batch(
                        engine_spec,
                        document,
                        "WorkerResponseParseError",
                        str(exc),
                    ),
                    "total_pipeline_ms": total_ms,
                    "resource_summary": resource_summary.model_dump(),
                    "exit_code": process.returncode,
                }

            return {
                "config_id": engine_spec.config_id,
                "document_id": document.document_id,
                "status": response.status.value,
                "success": response.success,
                "error_type": response.error_type,
                "error_message": response.error_message,
                "prepare_time_ms": response.prepare_time_ms,
                "total_pipeline_ms": total_ms,
                "resource_summary": resource_summary.model_dump(),
                "exit_code": process.returncode,
                "run_results": [result.model_dump(mode="json") for result in response.run_results],
            }

    @staticmethod
    def _failed_batch(
        engine_spec: EngineSpec,
        document: DocumentInput,
        error_type: str,
        error_message: str,
    ) -> dict[str, Any]:
        return {
            "config_id": engine_spec.config_id,
            "document_id": document.document_id,
            "status": EngineStatus.FAILED.value,
            "success": False,
            "error_type": error_type,
            "error_message": error_message,
            "prepare_time_ms": 0.0,
            "total_pipeline_ms": 0.0,
            "resource_summary": {},
            "run_results": [],
        }
