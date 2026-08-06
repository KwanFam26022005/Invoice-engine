"""Common Document IR (Intermediate Representation) and deterministic identifier helpers."""

from datetime import datetime, timezone
import hashlib
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from document_engine.core.models import PDFProfileType


def generate_document_id(file_sha256: str) -> str:
    """Generate deterministic document ID from SHA-256 hash."""
    clean_hash = file_sha256.lower().strip()
    return f"doc_{clean_hash[:16]}"


def generate_page_id(document_id: str, page_number: int) -> str:
    """Generate deterministic page ID."""
    return f"{document_id}_p{page_number:04d}"


def generate_block_id(page_id: str, block_index: int) -> str:
    """Generate deterministic block ID."""
    return f"{page_id}_b{block_index:05d}"


def generate_table_id(page_id: str, table_index: int) -> str:
    """Generate deterministic table ID."""
    return f"{page_id}_t{table_index:03d}"


def generate_cell_id(table_id: str, row_index: int, col_index: int) -> str:
    """Generate deterministic cell ID."""
    return f"{table_id}_r{row_index:03d}_c{col_index:03d}"


def generate_run_id(timestamp: Optional[datetime] = None, seed: str = "") -> str:
    """Generate processing run ID: YYYYMMDD_HHMMSS_<short_hash>."""
    if timestamp is None:
        timestamp = datetime.now(timezone.utc)
    ts_str = timestamp.strftime("%Y%m%d_%H%M%S")
    raw_hash = hashlib.sha256(f"{ts_str}_{seed}".encode("utf-8")).hexdigest()[:6]
    return f"{ts_str}_{raw_hash}"


class Geometry(BaseModel):
    bbox: List[float] = Field(
        default_factory=lambda: [0.0, 0.0, 0.0, 0.0],
        description="Rectangle coordinates [xmin, ymin, xmax, ymax]",
    )
    quad: Optional[List[float]] = None
    polygon: Optional[List[List[float]]] = None
    coordinate_system: str = "pdf_points_topleft"
    page_width: float = 0.0
    page_height: float = 0.0


class EvidenceReference(BaseModel):
    evidence_id: Optional[str] = None
    document_id: str
    page_number: int
    block_id: Optional[str] = None
    table_id: Optional[str] = None
    cell_id: Optional[str] = None
    bbox: Optional[List[float]] = None
    source_text: str = ""
    parser_id: str = ""
    parser_version: str = ""
    confidence: float = 1.0


class SourceDocument(BaseModel):
    document_id: str
    filename: str
    path: str
    mime_type: str = "application/pdf"
    sha256: str
    page_count: int
    received_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    source_metadata: Dict[str, Any] = Field(default_factory=dict)


class DocumentProfile(BaseModel):
    pdf_profile: PDFProfileType
    has_text_layer: bool
    text_character_count: int = 0
    text_density: float = 0.0
    image_count: int = 0
    full_page_image_ratio: float = 0.0
    requires_ocr: bool = False
    inspection_warnings: List[str] = Field(default_factory=list)


class TableCellIR(BaseModel):
    cell_id: str
    row_index: int
    col_index: int
    row_span: int = 1
    col_span: int = 1
    text: str = ""
    geometry: Optional[Geometry] = None
    is_header: bool = False


class TableIR(BaseModel):
    table_id: str
    page_number: int
    row_count: int
    col_count: int
    cells: List[TableCellIR] = Field(default_factory=list)
    headers: List[str] = Field(default_factory=list)
    geometry: Optional[Geometry] = None


class BlockIR(BaseModel):
    block_id: str
    page_number: int
    block_type: str = "text"
    text: str = ""
    reading_order: int = 0
    geometry: Optional[Geometry] = None
    font_metadata: Dict[str, Any] = Field(default_factory=dict)


class PageIR(BaseModel):
    page_id: str
    page_number: int
    width: float
    height: float
    blocks: List[BlockIR] = Field(default_factory=list)
    tables: List[TableIR] = Field(default_factory=list)
    text_content: str = ""


class ParserProvenance(BaseModel):
    parser_id: str
    parser_version: str
    parse_timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    execution_time_seconds: float = 0.0
    config: Dict[str, Any] = Field(default_factory=dict)


class ParseWarning(BaseModel):
    code: str
    message: str
    page_number: Optional[int] = None


class DocumentIR(BaseModel):
    document_id: str
    source_document: SourceDocument
    profile: DocumentProfile
    provenance: ParserProvenance
    pages: List[PageIR] = Field(default_factory=list)
    full_text: str = ""
    warnings: List[ParseWarning] = Field(default_factory=list)


class DocumentParseResult(BaseModel):
    success: bool
    document_ir: Optional[DocumentIR] = None
    error_message: Optional[str] = None
    warnings: List[ParseWarning] = Field(default_factory=list)
