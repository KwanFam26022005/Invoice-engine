"""Document evaluation, field auditing, and failure taxonomy package."""

from document_engine.evaluation.audit_models import (
    DocumentAuditSpec,
    FieldAuditEntry,
    FieldAuditStatus,
)
from document_engine.evaluation.comparator import compare_values
from document_engine.evaluation.failure_taxonomy import FailureCategory, FailureRecord
from document_engine.evaluation.metrics import (
    AggregateEvaluationReport,
    DocumentEvaluationSummary,
    Evaluator,
    FieldEvaluationResult,
)

__all__ = [
    "AggregateEvaluationReport",
    "DocumentAuditSpec",
    "DocumentEvaluationSummary",
    "Evaluator",
    "FailureCategory",
    "FailureRecord",
    "FieldAuditEntry",
    "FieldAuditStatus",
    "FieldEvaluationResult",
    "compare_values",
]
