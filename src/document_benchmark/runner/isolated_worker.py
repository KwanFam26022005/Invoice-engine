"""Isolated worker process entry point for document-engine benchmarks."""

import argparse
import json
import sys
import time
import traceback
from pathlib import Path

from document_benchmark.core.engine_registry import registry
from document_benchmark.core.statuses import EngineStatus
from document_benchmark.runner.worker_protocol import (
    WorkerRequest,
    WorkerResponse,
    WorkerRunResult,
)


def _write_response(path: Path, response: WorkerResponse) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(response.model_dump_json(indent=2), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Isolated DocumentEngine Worker")
    parser.add_argument("--request-file", required=True)
    args = parser.parse_args()

    request_path = Path(args.request_file)
    if not request_path.exists():
        sys.stderr.write(f"Request file does not exist: {request_path}\n")
        raise SystemExit(1)

    try:
        req = WorkerRequest(**json.loads(request_path.read_text(encoding="utf-8")))
    except Exception as exc:
        sys.stderr.write(f"Failed to parse WorkerRequest JSON: {exc}\n")
        raise SystemExit(1) from exc

    output_path = Path(req.output_file)
    registry.register_config(req.engine_spec)
    engine = None
    response = WorkerResponse(success=False, status=EngineStatus.FAILED)

    try:
        if req.action == "healthcheck":
            health = registry.healthcheck_config(req.engine_spec.config_id)
            response = WorkerResponse(
                success=health.available,
                status=health.status,
                health=health,
                error_message=health.error_message,
            )
        else:
            engine = registry.create_engine(req.engine_spec.config_id)
            prepare_started = time.perf_counter()
            engine.prepare()
            prepare_ms = (time.perf_counter() - prepare_started) * 1000.0

            total_runs = req.warmup_runs + req.measured_runs
            run_results: list[WorkerRunResult] = []

            for zero_based_index in range(total_runs):
                run_index = zero_based_index + 1
                is_warmup = run_index <= req.warmup_runs
                extract_started = time.perf_counter()
                try:
                    raw_result = engine.extract(req.document, target_schema=req.target_schema)
                    extract_ms = (time.perf_counter() - extract_started) * 1000.0
                    raw_result.run_id = req.run_id
                    success = bool(raw_result.success)
                    run_results.append(
                        WorkerRunResult(
                            run_index=run_index,
                            is_warmup=is_warmup,
                            success=success,
                            status=EngineStatus.SUCCESS if success else EngineStatus.FAILED,
                            extract_time_ms=round(extract_ms, 2),
                            error_type=raw_result.error_type,
                            error_message=raw_result.error_message,
                            raw_result=raw_result,
                        )
                    )
                except Exception as exc:
                    extract_ms = (time.perf_counter() - extract_started) * 1000.0
                    sys.stderr.write(
                        f"Extraction repeat {run_index} failed: {exc}\n{traceback.format_exc()}\n"
                    )
                    run_results.append(
                        WorkerRunResult(
                            run_index=run_index,
                            is_warmup=is_warmup,
                            success=False,
                            status=EngineStatus.FAILED,
                            extract_time_ms=round(extract_ms, 2),
                            error_type=type(exc).__name__,
                            error_message=str(exc),
                        )
                    )

            measured = [result for result in run_results if not result.is_warmup]
            measured_success = [result for result in measured if result.success]
            response = WorkerResponse(
                success=bool(measured) and len(measured_success) == len(measured),
                status=(
                    EngineStatus.SUCCESS
                    if measured and len(measured_success) == len(measured)
                    else EngineStatus.FAILED
                ),
                error_type=None if measured_success else "ExtractionError",
                error_message=None if measured_success else "No measured extraction completed successfully",
                prepare_time_ms=round(prepare_ms, 2),
                run_results=run_results,
            )
    except MemoryError as exc:
        response = WorkerResponse(
            success=False,
            status=EngineStatus.OUT_OF_MEMORY,
            error_type=type(exc).__name__,
            error_message=str(exc),
        )
    except Exception as exc:
        sys.stderr.write(f"Worker exception: {exc}\n{traceback.format_exc()}\n")
        response = WorkerResponse(
            success=False,
            status=EngineStatus.FAILED,
            error_type=type(exc).__name__,
            error_message=str(exc),
        )
    finally:
        if engine is not None:
            try:
                engine.close()
            except Exception as exc:
                sys.stderr.write(f"Engine close warning: {exc}\n")
        _write_response(output_path, response)


if __name__ == "__main__":
    main()
