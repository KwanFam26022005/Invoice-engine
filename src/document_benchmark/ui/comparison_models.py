"""Pydantic models for single-document engine comparison UI."""

from __future__ import annotations

from typing import Any
from pydantic import BaseModel, Field


class DocumentInfo(BaseModel):
    """Metadata for a benchmark document."""

    document_id: str
    filename: str
    category: str = "unknown"
    page_count: int = 1
    sha256: str = ""
    input_profile: str = "scan_ocr"
    ground_truth_level: int = 0
    benchmark_path: str = ""
    resolved_pdf_path: str | None = None
    pdf_available: bool = False
    pdf_error: str | None = None


class PerformanceRepeat(BaseModel):
    """Metrics for a single measured repeat."""

    run_index: int
    success: bool
    extract_time_ms: float = 0.0
    total_pipeline_ms: float = 0.0
    rss_peak_mb: float | None = None
    uss_peak_mb: float | None = None
    cpu_peak_percent: float | None = None
    status: str = "SUCCESS"
    error_type: str | None = None
    error_message: str | None = None


class PerformanceStats(BaseModel):
    """Aggregated performance statistics for an engine on a specific document."""

    measured_count: int = 0
    successful_count: int = 0
    failed_count: int = 0
    extract_ms_mean: float = 0.0
    extract_ms_median: float = 0.0
    extract_ms_min: float = 0.0
    extract_ms_max: float = 0.0
    extract_ms_p50: float = 0.0
    extract_ms_p95: float = 0.0
    extract_ms_std: float = 0.0
    extract_ms_cv: float = 0.0
    prepare_time_ms: float = 0.0
    total_pipeline_ms_mean: float = 0.0
    rss_peak_mb_max: float | None = None
    uss_peak_mb_max: float | None = None
    cpu_peak_percent_max: float | None = None
    cpu_metrics_valid: bool = True
    cpu_metrics_warning: str | None = None


class EngineView(BaseModel):
    """View model for a single engine configuration on a document."""

    config_id: str
    engine_name: str
    run_id: str
    run_dir: str
    success: bool
    correctness_run_index: int = 2
    raw_result_path: str = ""
    raw_json_size_bytes: int = 0
    full_text: str = ""
    char_count: int = 0
    word_count: int = 0
    line_count: int = 0
    page_count: int = 1
    table_count: int = 0
    field_candidates: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    runtime_class: str = "N/A"
    engine_generation: str = "N/A"
    benchmark_track: str = "N/A"
    ocr_enabled: bool = False
    ocr_engine: str | None = None
    ocr_languages: list[str] = Field(default_factory=list)
    package_versions_runtime: dict[str, str | None] = Field(default_factory=dict)
    package_versions_env: dict[str, str | None] = Field(default_factory=dict)
    provenance_mismatch: bool = False
    provenance_warnings: list[str] = Field(default_factory=list)
    performance_repeats: list[PerformanceRepeat] = Field(default_factory=list)
    performance_stats: PerformanceStats = Field(default_factory=PerformanceStats)
    logs_tail: list[str] = Field(default_factory=list)
    raw_payload: dict[str, Any] = Field(default_factory=dict)


class FieldComparisonItem(BaseModel):
    """Comparison item for a single extracted field candidate."""

    field_name: str
    docling_raw: Any = None
    pp_raw: Any = None
    docling_normalized: Any = None
    pp_normalized: Any = None
    status: str = "Khác biệt"  # Đồng thuận, Đồng thuận sau chuẩn hóa, Khác biệt, Chỉ có ở Docling, Chỉ có ở PP-StructureV3, Không có dữ liệu
    status_badge_color: str = "gray"
    evidence: str = ""
    requires_manual_check: bool = False
    validation_warning: str | None = None


class TableComparisonItem(BaseModel):
    """Comparison view model for extracted tables."""

    table_index: int
    page_number: int = 1
    docling_headers: list[str] = Field(default_factory=list)
    docling_rows: list[list[Any]] = Field(default_factory=list)
    pp_pred_html: str | None = None
    pp_parsed_headers: list[str] = Field(default_factory=list)
    pp_parsed_rows: list[list[Any]] = Field(default_factory=list)
    pp_cell_box_count: int = 0
    docling_row_count: int = 0
    docling_col_count: int = 0
    pp_row_count: int = 0
    pp_col_count: int = 0
    structural_similarity_score: float = 0.0
    structural_status: str = "Khác biệt"


class BoundingBox(BaseModel):
    """Geometry bounding box representation."""

    label: str
    box: list[float]  # [xmin, ymin, xmax, ymax]
    score: float | None = None
    box_type: str = "text"  # text, table, layout, cell
    source_engine: str = "docling"


class PageGeometry(BaseModel):
    """Geometry bounding boxes for a document page."""

    page_number: int
    width: float = 1.0
    height: float = 1.0
    boxes: list[BoundingBox] = Field(default_factory=list)
    coordinate_system_valid: bool = True
    coordinate_warning: str | None = None


class SelectedDocumentComparison(BaseModel):
    """Aggregated single-document comparison container for all tabs."""

    document: DocumentInfo
    docling_view: EngineView | None = None
    pp_view: EngineView | None = None
    text_similarity_ratio: float = 0.0
    field_comparisons: list[FieldComparisonItem] = Field(default_factory=list)
    table_comparisons: list[TableComparisonItem] = Field(default_factory=list)
    docling_geometry: dict[int, PageGeometry] = Field(default_factory=dict)
    pp_geometry: dict[int, PageGeometry] = Field(default_factory=dict)
    speed_ratio_mean: float | None = None  # docling_mean / pp_mean
    speed_ratio_p50: float | None = None
    campaign_id: str = ""
    dataset_fingerprint: str = ""
