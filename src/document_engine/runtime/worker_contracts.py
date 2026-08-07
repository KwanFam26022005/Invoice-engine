"""Contracts and schemas for isolated parser worker IPC communication over JSON."""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class WorkerRequest(BaseModel):
    request_id: str
    parser_id: str
    operation: str = "parse"  # "parse" or "healthcheck"
    input_path: str = ""
    document_id: str = ""
    page_count: int = 1
    options: Dict[str, Any] = Field(default_factory=dict)
    allow_model_download: bool = False


class WorkerResponse(BaseModel):
    request_id: str
    success: bool
    actual_parser_id: str
    actual_parser_version: str = "0.0.0"
    runtime_versions: Dict[str, str] = Field(default_factory=dict)
    document_ir_dict: Optional[Dict[str, Any]] = None
    health_data: Optional[Dict[str, Any]] = None
    warnings: List[Dict[str, Any]] = Field(default_factory=list)
    error_type: Optional[str] = None
    error_message: Optional[str] = None
