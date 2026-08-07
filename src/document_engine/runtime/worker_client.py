"""Client manager for launching isolated parser subprocess workers safely without shell=True."""

import json
import logging
import os
from pathlib import Path
import subprocess
import sys
from typing import Optional

from document_engine.runtime.worker_contracts import WorkerRequest, WorkerResponse
from document_engine.runtime.worker_errors import (
    WorkerExecutionError,
    WorkerNotFoundError,
    WorkerTimeoutError,
)

logger = logging.getLogger(__name__)


def resolve_worker_python(parser_id: str, repository_root: Optional[Path] = None) -> str:
    """Resolve a dedicated worker interpreter independently of the process CWD."""
    root = repository_root or Path(__file__).resolve().parents[3]
    contracts = {
        "docling_native": ("DOCLING_WORKER_PYTHON", ".venv-docling"),
        "docling_ocr": ("DOCLING_WORKER_PYTHON", ".venv-docling"),
        "docling_semantic": (
            "DOCLING_SEMANTIC_WORKER_PYTHON",
            ".venv-docling-semantic",
        ),
        "paddleocr_vl": ("PADDLE_WORKER_PYTHON", ".venv-paddlevl"),
    }
    if parser_id not in contracts:
        return sys.executable

    override_name, venv_name = contracts[parser_id]
    env_override = os.getenv(override_name)
    if env_override and Path(env_override).is_file():
        return str(Path(env_override).resolve())

    candidates = (
        root / venv_name / "Scripts" / "python.exe",
        root / venv_name / "bin" / "python",
    )
    for candidate in candidates:
        if candidate.is_file():
            return str(candidate.resolve())

    raise WorkerNotFoundError(
        f"Dedicated worker interpreter for '{parser_id}' is unavailable under {venv_name}."
    )


def resolve_worker_script(parser_id: str) -> str:
    """Resolve worker script entrypoint."""
    root_dir = Path(__file__).resolve().parents[2]
    if parser_id in ("docling_native", "docling_ocr"):
        script_path = root_dir / "document_engine" / "workers" / "docling_worker.py"
    elif parser_id == "docling_semantic":
        script_path = root_dir / "document_engine" / "workers" / "docling_semantic_worker.py"
    elif parser_id == "paddleocr_vl":
        script_path = root_dir / "document_engine" / "workers" / "paddleocr_vl_worker.py"
    else:
        raise WorkerNotFoundError(f"No worker script defined for parser_id: '{parser_id}'")

    if not script_path.exists():
        raise WorkerNotFoundError(f"Worker script does not exist at: {script_path}")

    return str(script_path)


class WorkerClient:
    def __init__(self, default_timeout: float = 120.0):
        self.default_timeout = default_timeout

    def execute_worker(
        self, request: WorkerRequest, timeout: Optional[float] = None
    ) -> WorkerResponse:
        """Execute isolated worker via subprocess using list argv (no shell=True)."""
        timeout_sec = timeout or self.default_timeout
        python_bin = resolve_worker_python(request.parser_id)
        script_path = resolve_worker_script(request.parser_id)

        cmd = [python_bin, script_path]

        req_json = request.model_dump_json()

        try:
            process = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                shell=False,
            )

            stdout_data, stderr_data = process.communicate(
                input=req_json, timeout=timeout_sec
            )

            if stderr_data:
                # Log stderr messages without dumping full OCR text
                lines = stderr_data.strip().splitlines()
                summary_lines = lines[:5] + (["..."] if len(lines) > 5 else [])
                logger.debug(
                    "Worker stderr [%s]: %s",
                    request.parser_id,
                    " | ".join(summary_lines),
                )

            if process.returncode != 0 and not stdout_data:
                return WorkerResponse(
                    request_id=request.request_id,
                    success=False,
                    actual_parser_id=request.parser_id,
                    error_type="WORKER_PROCESS_ERROR",
                    error_message=f"Worker process exited with code {process.returncode}: {stderr_data[:500]}",
                )

            if not stdout_data.strip():
                return WorkerResponse(
                    request_id=request.request_id,
                    success=False,
                    actual_parser_id=request.parser_id,
                    error_type="EMPTY_WORKER_OUTPUT",
                    error_message="Worker stdout returned empty response.",
                )

            # Parse JSON output from stdout
            try:
                data = json.loads(stdout_data)
                return WorkerResponse.model_validate(data)
            except Exception as parse_err:
                return WorkerResponse(
                    request_id=request.request_id,
                    success=False,
                    actual_parser_id=request.parser_id,
                    error_type="INVALID_WORKER_JSON",
                    error_message=f"Failed to parse worker stdout JSON: {parse_err}. Output preview: {stdout_data[:200]}",
                )

        except subprocess.TimeoutExpired:
            process.kill()
            process.communicate()
            raise WorkerTimeoutError(
                f"Worker '{request.parser_id}' timed out after {timeout_sec}s"
            )
        except Exception as e:
            if isinstance(e, (WorkerNotFoundError, WorkerTimeoutError)):
                raise
            raise WorkerExecutionError(f"Failed to launch worker subprocess: {e}") from e
