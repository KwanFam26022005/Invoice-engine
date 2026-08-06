"""Common document envelope and base schema definitions."""

from typing import Any, Optional
from pydantic import BaseModel, ConfigDict, Field

from document_benchmark.core.statuses import DocumentFamily, DocumentSubtype


class DocumentEnvelope(BaseModel):
    """Envelope wrapping normalized canonical document extraction results."""

    model_config = ConfigDict(extra="ignore")

    document_id: str
    filename: str
    sha256: str
    page_count: int = 1
    document_family: DocumentFamily = DocumentFamily.UNKNOWN
    document_subtype: Optional[DocumentSubtype] = DocumentSubtype.UNKNOWN
    language: str = "vi"
    source_engine: str = ""
    source_config: str = ""
    requires_review: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)
