"""Private ground-truth audit models for document evaluation."""

from enum import Enum
from typing import Any, Dict, Optional
from pydantic import BaseModel, Field


class FieldAuditStatus(str, Enum):
    CONFIRMED = "CONFIRMED"
    NOT_PRESENT_IN_SOURCE = "NOT_PRESENT_IN_SOURCE"
    AMBIGUOUS_SOURCE = "AMBIGUOUS_SOURCE"
    NOT_AUDITED = "NOT_AUDITED"


class FieldAuditEntry(BaseModel):
    expected: Optional[Any] = None
    status: FieldAuditStatus = FieldAuditStatus.CONFIRMED
    notes: Optional[str] = None


class DocumentAuditSpec(BaseModel):
    document_id: str
    family: str
    expected_profile: Optional[str] = None
    fields: Dict[str, FieldAuditEntry] = Field(default_factory=dict)
