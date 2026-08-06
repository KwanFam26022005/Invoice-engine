"""IPC Worker Protocol contracts for isolated engine process execution."""


from pydantic import BaseModel, ConfigDict

from document_benchmark.core.contracts import (
    DocumentInput,
    EngineHealth,
    EngineSpec,
    RawExtractionResult,
)
from document_benchmark.core.statuses import EngineStatus


class WorkerRequest(BaseModel):
    """Payload sent from Benchmark Controller to Isolated Worker."""

    model_config = ConfigDict(extra="ignore")

    run_id: str
    engine_spec: EngineSpec
    document: DocumentInput
    action: str = "extract"  # "healthcheck", "prepare_and_extract", "extract"
    target_schema: dict | None = None
    output_file: str


class WorkerResponse(BaseModel):
    """Payload written by Isolated Worker to output_file JSON."""

    model_config = ConfigDict(extra="ignore")

    success: bool
    status: EngineStatus
    error_type: str | None = None
    error_message: str | None = None
    prepare_time_ms: float = 0.0
    extract_time_ms: float = 0.0
    raw_result: RawExtractionResult | None = None
    health: EngineHealth | None = None
