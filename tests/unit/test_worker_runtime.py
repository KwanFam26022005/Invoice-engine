"""Unit tests for isolated worker runtime, IPC contracts, and error handling."""

import os
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


def test_resolve_worker_python():
    docling_python = resolve_worker_python("docling_native")
    assert docling_python is not None

    paddle_python = resolve_worker_python("paddleocr_vl")
    assert paddle_python is not None


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
