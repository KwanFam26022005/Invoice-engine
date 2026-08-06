"""Base DocumentEngine interface protocol and abstract class."""

from abc import ABC, abstractmethod
from typing import Protocol, runtime_checkable

from document_benchmark.core.contracts import (
    DocumentInput,
    EngineHealth,
    EngineSpec,
    RawExtractionResult,
)


@runtime_checkable
class DocumentEngine(Protocol):
    """Protocol that all document extraction engines must implement."""

    spec: EngineSpec

    def healthcheck(self) -> EngineHealth:
        """Perform lightweight check without downloading heavy model files."""
        ...

    def prepare(self) -> None:
        """Load engine models/weights into memory. Separate from extract()."""
        ...

    def extract(
        self,
        document: DocumentInput,
        target_schema: dict | None = None,
    ) -> RawExtractionResult:
        """Extract content from a document into RawExtractionResult."""
        ...

    def close(self) -> None:
        """Release models, memory, and temp file resources."""
        ...


class BaseDocumentEngine(ABC):
    """Abstract base class providing standard error handling and timing boilerplate."""

    def __init__(self, spec: EngineSpec) -> None:
        self.spec = spec
        self._is_prepared = False

    @abstractmethod
    def healthcheck(self) -> EngineHealth:
        """Perform lightweight healthcheck."""

    @abstractmethod
    def prepare(self) -> None:
        """Load model into memory."""

    @abstractmethod
    def extract(
        self,
        document: DocumentInput,
        target_schema: dict | None = None,
    ) -> RawExtractionResult:
        """Perform extraction."""

    def close(self) -> None:
        """Clean up resources."""
        self._is_prepared = False
