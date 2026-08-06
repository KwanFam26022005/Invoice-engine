"""Exception taxonomy for the document benchmark pipeline."""

from typing import Any


class BenchmarkError(Exception):
    """Base exception for all benchmark errors."""

    def __init__(
        self,
        message: str,
        code: str = "BENCHMARK_ERROR",
        engine_id: str | None = None,
        document_id: str | None = None,
        phase: str | None = None,
        recoverable: bool = False,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.engine_id = engine_id
        self.document_id = document_id
        self.phase = phase
        self.recoverable = recoverable
        self.details = details or {}

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "engine_id": self.engine_id,
            "document_id": self.document_id,
            "phase": self.phase,
            "recoverable": self.recoverable,
            "details": self.details,
        }


class InvalidInputError(BenchmarkError):
    def __init__(self, message: str, **kwargs: Any) -> None:
        kwargs.setdefault("code", "INVALID_INPUT_ERROR")
        super().__init__(message, **kwargs)


class UnsupportedDocumentError(BenchmarkError):
    def __init__(self, message: str, **kwargs: Any) -> None:
        kwargs.setdefault("code", "UNSUPPORTED_DOCUMENT_ERROR")
        super().__init__(message, **kwargs)


class EngineUnavailableError(BenchmarkError):
    def __init__(self, message: str, **kwargs: Any) -> None:
        kwargs.setdefault("code", "ENGINE_UNAVAILABLE_ERROR")
        super().__init__(message, **kwargs)


class EnginePreparationError(BenchmarkError):
    def __init__(self, message: str, **kwargs: Any) -> None:
        kwargs.setdefault("code", "ENGINE_PREPARATION_ERROR")
        super().__init__(message, **kwargs)


class ExtractionError(BenchmarkError):
    def __init__(self, message: str, **kwargs: Any) -> None:
        kwargs.setdefault("code", "EXTRACTION_ERROR")
        super().__init__(message, **kwargs)


class EngineTimeoutError(BenchmarkError):
    def __init__(self, message: str, **kwargs: Any) -> None:
        kwargs.setdefault("code", "ENGINE_TIMEOUT_ERROR")
        super().__init__(message, **kwargs)


class EngineOutOfMemoryError(BenchmarkError):
    def __init__(self, message: str, **kwargs: Any) -> None:
        kwargs.setdefault("code", "ENGINE_OUT_OF_MEMORY_ERROR")
        super().__init__(message, **kwargs)


class NormalizationError(BenchmarkError):
    def __init__(self, message: str, **kwargs: Any) -> None:
        kwargs.setdefault("code", "NORMALIZATION_ERROR")
        super().__init__(message, **kwargs)


class ValidationError(BenchmarkError):
    def __init__(self, message: str, **kwargs: Any) -> None:
        kwargs.setdefault("code", "VALIDATION_ERROR")
        super().__init__(message, **kwargs)


class ExportError(BenchmarkError):
    def __init__(self, message: str, **kwargs: Any) -> None:
        kwargs.setdefault("code", "EXPORT_ERROR")
        super().__init__(message, **kwargs)
