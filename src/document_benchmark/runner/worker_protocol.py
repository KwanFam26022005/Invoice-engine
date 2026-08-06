"""IPC contracts for isolated document-engine execution."""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from document_benchmark.core.contracts import (
    DocumentInput,
    EngineHealth,
    EngineSpec,
    RawExtractionResult,
)
from document_benchmark.core.statuses import EngineStatus


class WorkerRequest(BaseModel):
    """Payload sent from the benchmark controller to an isolated worker."""

    model_config = ConfigDict(extra="ignore")

    run_id: str
    engine_spec: EngineSpec
    document: DocumentInput
    action: str = "benchmark"
    target_schema: dict[str, Any] | None = None
    output_file: str
    warmup_runs: int = 0
    measured_runs: int = 1
    reuse_prepared_engine: bool = True


class WorkerRunResult(BaseModel):
    """Timing and extraction result for one repeat inside a worker process."""

    model_config = ConfigDict(extra="ignore")

    run_index: int
    is_warmup: bool
    success: bool
    status: EngineStatus
    extract_time_ms: float = 0.0
    error_type: str | None = None
    error_message: str | None = None
    raw_result: RawExtractionResult | None = None


class WorkerResponse(BaseModel):
    """Payload written by the isolated worker to its response JSON file."""

    model_config = ConfigDict(extra="ignore")

    success: bool
    status: EngineStatus
    error_type: str | None = None
    error_message: str | None = None
    prepare_time_ms: float = 0.0
    run_results: list[WorkerRunResult] = Field(default_factory=list)
    health: EngineHealth | None = None
