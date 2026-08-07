"""Exceptions for Document Engine."""


class DocumentEngineError(Exception):
    """Base exception for all Document Engine errors."""


class IntakeError(DocumentEngineError):
    """Raised when document intake or inspection fails."""


class InvalidPDFError(IntakeError):
    """Raised when PDF file is invalid, corrupt, or missing magic bytes."""


class ParserError(DocumentEngineError):
    """Raised when document parsing fails."""


class ParserNotFoundError(ParserError):
    """Raised when requested parser is not registered or available."""


class RoutingError(DocumentEngineError):
    """Raised when parser router fails to select a valid parser."""


class ClassificationError(DocumentEngineError):
    """Raised when document family classification fails."""


class ValidationError(DocumentEngineError):
    """Raised when deterministic validation encounters an invalid structure."""


class StorageError(DocumentEngineError):
    """Raised when DuckDB persistence fails."""


class ExportError(DocumentEngineError):
    """Raised when exporting to Excel or JSON fails."""
