"""Isolated worker process entry point. Executes DocumentEngine in isolated process."""

import argparse
import json
import sys
import time
import traceback
from pathlib import Path

from document_benchmark.core.contracts import RawExtractionResult
from document_benchmark.core.engine_registry import registry
from document_benchmark.core.statuses import EngineStatus
from document_benchmark.runner.worker_protocol import WorkerRequest, WorkerResponse


def main() -> None:
    parser = argparse.ArgumentParser(description="Isolated DocumentEngine Worker")
    parser.add_argument(
        "--request-file",
        required=True,
        help="Path to JSON file containing WorkerRequest",
    )
    args = parser.parse_args()

    request_path = Path(args.request_file)
    if not request_path.exists():
        sys.stderr.write(f"Request file does not exist: {args.request_file}\n")
        sys.exit(1)

    try:
        with open(request_path, "r", encoding="utf-8") as f:
            req_data = json.load(f)
        req = WorkerRequest(**req_data)
    except Exception as e:
        sys.stderr.write(f"Failed to parse WorkerRequest JSON: {e}\n")
        sys.exit(1)

    output_path = Path(req.output_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Register spec dynamically in worker's registry
    registry.register_config(req.engine_spec)

    response = WorkerResponse(
        success=False,
        status=EngineStatus.FAILED,
    )

    engine = None
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
            # Instantiate engine
            engine = registry.create_engine(req.engine_spec.config_id)

            # Measure prepare phase
            prep_start = time.perf_counter()
            engine.prepare()
            prep_ms = (time.perf_counter() - prep_start) * 1000.0

            # Measure extract phase
            ext_start = time.perf_counter()
            raw_res: RawExtractionResult = engine.extract(
                req.document, target_schema=req.target_schema
            )
            ext_ms = (time.perf_counter() - ext_start) * 1000.0
            raw_res.run_id = req.run_id

            if raw_res.success:
                response = WorkerResponse(
                    success=True,
                    status=EngineStatus.SUCCESS,
                    prepare_time_ms=round(prep_ms, 2),
                    extract_time_ms=round(ext_ms, 2),
                    raw_result=raw_res,
                )
            else:
                response = WorkerResponse(
                    success=False,
                    status=EngineStatus.FAILED,
                    error_type=raw_res.error_type or "ExtractionError",
                    error_message=raw_res.error_message or "Extraction failed",
                    prepare_time_ms=round(prep_ms, 2),
                    extract_time_ms=round(ext_ms, 2),
                    raw_result=raw_res,
                )

    except Exception as e:
        tb = traceback.format_exc()
        sys.stderr.write(f"Worker exception: {e}\n{tb}\n")
        response = WorkerResponse(
            success=False,
            status=EngineStatus.FAILED,
            error_type=type(e).__name__,
            error_message=str(e),
        )
    finally:
        if engine is not None:
            try:
                engine.close()
            except Exception:
                pass

        # Write WorkerResponse JSON to output file
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(response.model_dump_json(indent=2))


if __name__ == "__main__":
    main()
