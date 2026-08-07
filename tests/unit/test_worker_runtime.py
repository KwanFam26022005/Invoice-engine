"""Unit tests for isolated worker runtime, IPC contracts, and error handling."""

import pytest
from document_engine.runtime.worker_client import WorkerClient, resolve_worker_python
from document_engine.runtime.worker_contracts import WorkerRequest, WorkerResponse
from document_engine.runtime.worker_errors import WorkerNotFoundError


def test_worker_request_response_contracts():
    req = WorkerRequest(
        request_id="test_001",
        parser_id="docling_native",
        input_path="dummy.pdf",
        document_id="doc_123",
        options={"do_ocr": False},
    )
    json_data = req.model_dump_json()
    assert "test_001" in json_data
    assert "docling_native" in json_data

    resp = WorkerResponse(
        request_id="test_001",
        success=True,
        actual_parser_id="docling_native",
        actual_parser_version="2.0.0",
        runtime_versions={"python": "3.11.0"},
    )
    assert resp.success is True
    assert resp.actual_parser_id == "docling_native"


def test_worker_request_healthcheck_operation():
    req = WorkerRequest(
        request_id="test_hc_001",
        parser_id="paddleocr_vl",
        operation="healthcheck",
    )
    assert req.operation == "healthcheck"
    assert "operation" in req.model_dump_json()


def test_resolve_worker_python_windows_venv_is_independent_of_cwd(tmp_path, monkeypatch):
    interpreter = tmp_path / ".venv-docling" / "Scripts" / "python.exe"
    interpreter.parent.mkdir(parents=True)
    interpreter.touch()
    monkeypatch.chdir(tmp_path.parent)

    resolved = resolve_worker_python("docling_native", repository_root=tmp_path)

    assert resolved == str(interpreter.resolve())


def test_resolve_worker_python_posix_venv(tmp_path):
    interpreter = tmp_path / ".venv-docling" / "bin" / "python"
    interpreter.parent.mkdir(parents=True)
    interpreter.touch()

    assert resolve_worker_python("docling_ocr", repository_root=tmp_path) == str(
        interpreter.resolve()
    )


def test_resolve_worker_python_prefers_valid_override(tmp_path, monkeypatch):
    dedicated = tmp_path / ".venv-docling" / "Scripts" / "python.exe"
    dedicated.parent.mkdir(parents=True)
    dedicated.touch()
    override = tmp_path / "override-python.exe"
    override.touch()
    monkeypatch.setenv("DOCLING_WORKER_PYTHON", str(override))

    assert resolve_worker_python("docling_ocr", repository_root=tmp_path) == str(
        override.resolve()
    )


def test_resolve_worker_python_rejects_missing_dedicated_environment(tmp_path):
    with pytest.raises(WorkerNotFoundError):
        resolve_worker_python("docling_ocr", repository_root=tmp_path)


def test_worker_client_unavailable_script():
    client = WorkerClient(default_timeout=5.0)
    req = WorkerRequest(
        request_id="test_002",
        parser_id="nonexistent_parser",
        input_path="dummy.pdf",
        document_id="doc_456",
    )
    with pytest.raises(WorkerNotFoundError):
        client.execute_worker(req)
