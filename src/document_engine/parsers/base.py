"""Abstract base class contract for document parsers."""

from abc import ABC, abstractmethod
from typing import Any, Dict, List
from pydantic import BaseModel, Field

from document_engine.core.models import PDFProfileType
from document_engine.ir.models import DocumentParseResult, DocumentProfile, SourceDocument


class ParserSpec(BaseModel):
    parser_id: str
    name: str
    version: str = "1.0.0"
    supported_profiles: List[PDFProfileType] = Field(default_factory=list)
    requires_gpu: bool = False
    is_fallback: bool = False
    config: Dict[str, Any] = Field(default_factory=dict)


class ParserHealth(BaseModel):
    parser_id: str
    healthy: bool
    message: str = ""
    dependencies_available: bool = True


class DocumentParser(ABC):
    """Abstract interface for all document parsers."""

    @property
    @abstractmethod
    def spec(self) -> ParserSpec:
        """Get parser specification."""

    @property
    def parser_id(self) -> str:
        return self.spec.parser_id

    @abstractmethod
    def healthcheck(self) -> ParserHealth:
        """Check if parser dependencies and environment are ready."""

    @abstractmethod
    def supports(self, profile: DocumentProfile) -> bool:
        """Check if parser supports the given document profile."""

    def prepare(self) -> None:
        """Pre-load model weights or initialize context if needed."""

    @abstractmethod
    def parse(self, document: SourceDocument, profile: DocumentProfile) -> DocumentParseResult:
        """Parse source document into Common Document IR."""

    def close(self) -> None:
        """Clean up resources."""
