"""Error definitions for isolated parser worker executions."""

from document_engine.core.exceptions import DocumentEngineError


class WorkerError(DocumentEngineError):
    """Base error for worker execution failures."""
    pass


class WorkerNotFoundError(WorkerError):
    """Raised when worker script or python interpreter is not found."""
    pass


class WorkerTimeoutError(WorkerError):
    """Raised when a worker process exceeds execution timeout."""
    pass


class WorkerExecutionError(WorkerError):
    """Raised when worker returns error response or non-zero exit code."""
    pass


class ParserUnavailableError(WorkerError):
    """Raised when requested parser dependencies or offline model caches are missing."""
    pass
