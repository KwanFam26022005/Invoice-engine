"""Core status enums and execution models for Document Engine."""

from enum import Enum
from typing import Any, Dict, Optional
from pydantic import BaseModel, Field


class PDFProfileType(str, Enum):
    NATIVE_PDF = "native_pdf"
    SCAN_PDF = "scan_pdf"
    MIXED_PDF = "mixed_pdf"
    INVALID_PDF = "invalid_pdf"


class DocumentFamilyType(str, Enum):
    SALES_INVOICE = "sales_invoice"
    UTILITY_CONSUMPTION_INVOICE = "utility_consumption_invoice"
    SERVICE_VOLUME_INVOICE = "service_volume_invoice"
    PORT_SERVICE_INVOICE = "port_service_invoice"
    RECEIPT = "receipt"
    TAX_WITHHOLDING_CERTIFICATE = "tax_withholding_certificate"
    SUPPORTING_STATEMENT = "supporting_statement"
    UNKNOWN = "unknown"


class SourceFormatType(str, Enum):
    ELECTRONIC_DOCUMENT = "electronic_document"
    SCANNED_PAPER = "scanned_paper"
    UNKNOWN = "unknown"


class ValidationSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class ProcessingStatus(str, Enum):
    RECEIVED = "received"
    INSPECTED = "inspected"
    PARSED = "parsed"
    CLASSIFIED = "classified"
    MAPPED = "mapped"
    VALIDATED = "validated"
    COMPLETED = "completed"
    REVIEW_REQUIRED = "review_required"
    FAILED = "failed"


class ReviewStatus(str, Enum):
    PENDING = "pending"
    IN_REVIEW = "in_review"
    ACCEPTED = "accepted"
    CORRECTED = "corrected"
    REJECTED = "rejected"


class ProcessingSummary(BaseModel):
    received: int = 0
    processed: int = 0
    accepted: int = 0
    review_required: int = 0
    failed: int = 0
    duplicates: int = 0
    unknown: int = 0
    details: Dict[str, Any] = Field(default_factory=dict)
