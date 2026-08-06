"""Reproducible smoke-benchmark planning, execution, and reporting."""

from document_benchmark.smoke.dataset import SmokeDataset, SmokeDatasetError, load_smoke_dataset
from document_benchmark.smoke.preflight import EnginePreflightResult, run_engine_preflight
from document_benchmark.smoke.report import write_campaign_reports

__all__ = [
    "EnginePreflightResult",
    "SmokeDataset",
    "SmokeDatasetError",
    "load_smoke_dataset",
    "run_engine_preflight",
    "write_campaign_reports",
]
