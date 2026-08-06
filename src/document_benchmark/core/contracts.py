"""Pydantic core data contracts for the document benchmark pipeline."""

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from document_benchmark.core.statuses import (
    CachePolicy,
    DocumentFamily,
    DocumentSubtype,
    EngineStatus,
    ExecutionMode,
    OutputKind,
)


class EngineSpec(BaseModel):
    """Specification of an engine configuration candidate."""

    model_config = ConfigDict(extra="ignore")

    engine_id: str
    engine_version: str = "1.0.0"
    config_id: str
    output_kind: OutputKind = OutputKind.DOCUMENT_IR
    supports_pdf_text: bool = True
    supports_scanned_pdf: bool = False
    supports_images: bool = False
    supports_tables: bool = True
    supports_gpu: bool = False
    supports_multi_page: bool = True
    provides_bounding_boxes: bool = False
    license_name: str = "Proprietary"
    enabled: bool = True
    device: str = "cpu"
    options: dict[str, Any] = Field(default_factory=dict)


class EngineHealth(BaseModel):
    """Health check status of a document engine."""

    model_config = ConfigDict(extra="ignore")

    engine_id: str
    config_id: str
    status: EngineStatus
    available: bool
    error_message: str | None = None
    missing_dependencies: list[str] = Field(default_factory=list)
    runtime_metadata: dict[str, Any] = Field(default_factory=dict)


class DocumentInput(BaseModel):
    """Normalized specification of an input PDF document."""

    model_config = ConfigDict(extra="ignore")

    document_id: str
    path: str
    mime_type: str = "application/pdf"
    filename: str
    sha256: str
    page_count: int = 1
    metadata: dict[str, Any] = Field(default_factory=dict)


class RawExtractionResult(BaseModel):
    """Raw extraction result output by a DocumentEngine adapter."""

    model_config = ConfigDict(extra="ignore")

    run_id: str
    document_id: str
    engine_id: str
    config_id: str
    output_kind: OutputKind = OutputKind.DOCUMENT_IR
    success: bool
    error_type: str | None = None
    error_message: str | None = None
    raw_payload: dict[str, Any] = Field(default_factory=dict)
    full_text: str = ""
    pages: list[dict[str, Any]] = Field(default_factory=list)
    tables: list[dict[str, Any]] = Field(default_factory=list)
    field_candidates: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    started_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    execution_time_ms: float = 0.0


class CanonicalExtractionResult(BaseModel):
    """Normalized payload conforming to business schemas."""

    model_config = ConfigDict(extra="ignore")

    document_id: str
    document_family: DocumentFamily = DocumentFamily.UNKNOWN
    document_subtype: DocumentSubtype | None = DocumentSubtype.UNKNOWN
    canonical_payload: dict[str, Any] = Field(default_factory=dict)
    field_evidence: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    validation_issues: list[dict[str, Any]] = Field(default_factory=list)
    requires_review: bool = False
    source_engine: str = ""
    source_config: str = ""


class BenchmarkRunSpec(BaseModel):
    """Specification for running a benchmark execution."""

    model_config = ConfigDict(extra="ignore")

    run_id: str
    document_ids: list[str] = Field(default_factory=list)
    engine_config_ids: list[str] = Field(default_factory=list)
    execution_mode: ExecutionMode = ExecutionMode.BOTH
    device: str = "cpu"
    timeout_seconds: int = 120
    warmup_runs: int = 1
    measured_runs: int = 3
    resource_sample_interval_ms: int = 200
    cache_policy: CachePolicy = CachePolicy.COLD_CLEAN
    random_seed: int = 42


class ResourceSample(BaseModel):
    """Single hardware resource metric sample captured during run."""

    model_config = ConfigDict(extra="ignore")

    timestamp: float
    process_id: int
    cpu_percent: float
    rss_mb: float
    uss_mb: float
    vms_mb: float
    read_bytes: int
    write_bytes: int
    thread_count: int
    gpu_util_percent: float | None = None
    gpu_memory_util_percent: float | None = None
    gpu_vram_mb: float | None = None
    gpu_power_watts: float | None = None


class ResourceSummary(BaseModel):
    """Aggregated resource utilization for an engine execution."""

    model_config = ConfigDict(extra="ignore")

    cpu_avg_percent: float = 0.0
    cpu_peak_percent: float = 0.0
    rss_peak_mb: float = 0.0
    uss_peak_mb: float = 0.0
    vms_peak_mb: float = 0.0
    read_bytes_total: int = 0
    write_bytes_total: int = 0
    peak_thread_count: int = 0
    gpu_util_avg_percent: float | None = None
    gpu_memory_util_avg_percent: float | None = None
    gpu_vram_peak_mb: float | None = None
    sample_count: int = 0
