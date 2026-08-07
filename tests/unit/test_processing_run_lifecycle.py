"""Regression tests for processing-run completion accounting."""

from pathlib import Path
from unittest.mock import Mock

import pytest

from document_engine.orchestration.pipeline import DocumentPipeline, PipelineResult


def _pipeline_with_results(results):
    pipeline = DocumentPipeline.__new__(DocumentPipeline)
    pipeline.storage = Mock()
    iterator = iter(results)

    def process_file(*_args, **_kwargs):
        result = next(iterator)
        if isinstance(result, Exception):
            raise result
        return result

    pipeline.process_file = process_file
    return pipeline


def _result(status="accepted"):
    return PipelineResult(
        document_id="synthetic-doc",
        pdf_profile="native_pdf",
        selected_parser="synthetic",
        document_family="sales_invoice",
        validation_status=status,
        requires_review=status != "accepted",
        database_path="memory",
    )


@pytest.mark.parametrize(
    ("outcomes", "expected_processed", "expected_failed"),
    [
        ([_result(), _result()], 2, 0),
        ([_result(), RuntimeError("synthetic")], 1, 1),
        ([RuntimeError("synthetic"), RuntimeError("synthetic")], 0, 2),
    ],
)
def test_folder_run_completes_when_every_file_is_handled(
    tmp_path: Path, outcomes, expected_processed, expected_failed
):
    for index in range(len(outcomes)):
        (tmp_path / f"synthetic-{index}.pdf").touch()
    pipeline = _pipeline_with_results(outcomes)

    summary, _ = pipeline.process_folder(tmp_path, run_id="synthetic-run")

    assert summary.processed == expected_processed
    assert summary.failed == expected_failed
    assert pipeline.storage.update_processing_run.call_args.kwargs["status"] == "completed"


def test_empty_folder_completes_immediately(tmp_path: Path):
    pipeline = _pipeline_with_results([])

    summary, results = pipeline.process_folder(tmp_path, run_id="empty-run")

    assert summary.received == 0
    assert results == []
    assert pipeline.storage.update_processing_run.call_args.kwargs == {
        "run_id": "empty-run",
        "processed_count": 0,
        "accepted_count": 0,
        "review_required_count": 0,
        "failed_count": 0,
        "status": "completed",
    }
