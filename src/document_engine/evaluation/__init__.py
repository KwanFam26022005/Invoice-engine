"""Document evaluation, field auditing, failure taxonomy, and Phase 9 contracts."""

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
from document_engine.evaluation.phase9f import (
    Phase9EvaluationPath,
    Phase9FDocumentObservation,
    Phase9FExecutionPlan,
    Phase9FPathSummary,
    Phase9FRunContract,
    aggregate_phase9f_observations,
    build_phase9f_plan,
    validate_private_manifest_files,
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
    "Phase9EvaluationPath",
    "Phase9FDocumentObservation",
    "Phase9FExecutionPlan",
    "Phase9FPathSummary",
    "Phase9FRunContract",
    "aggregate_phase9f_observations",
    "build_phase9f_plan",
    "compare_values",
    "validate_private_manifest_files",
]
