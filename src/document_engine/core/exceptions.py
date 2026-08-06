"""Exceptions for Document Engine."""


class DocumentEngineError(Exception):
    """Base exception for all Document Engine errors."""

    pass


class IntakeError(DocumentEngineError):
    """Raised when document intake or inspection fails."""

    pass


class InvalidPDFError(IntakeError):
    """Raised when PDF file is invalid, corrupt, or missing magic bytes."""

    pass


class ParserError(DocumentEngineError):
    """Raised when document parsing fails."""

    pass


class ParserNotFoundError(ParserError):
    """Raised when requested parser is not registered or available."""

    pass


class RoutingError(DocumentEngineError):
    """Raised when parser router fails to select a valid parser."""

    pass


class ClassificationError(DocumentEngineError):
    """Raised when document family classification fails."""

    pass


class ValidationError(DocumentEngineError):
    """Raised when deterministic validation encounters an invalid structure."""

    pass


class StorageError(DocumentEngineError):
    """Raised when DuckDB persistence fails."""

    pass


class ExportError(DocumentEngineError):
    """Raised when exporting to Excel or JSON fails."""

    pass
