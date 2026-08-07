"""Schema-conditioned semantic extraction and evidence-grounding contracts."""

from document_engine.semantic.contracts import (
    SemanticCandidate,
    SemanticCandidateStatus,
    SemanticEvidenceHint,
    SemanticExtractionPolicy,
    SemanticExtractionRequest,
    SemanticExtractionResult,
    SemanticExtractor,
)
from document_engine.semantic.flatten import flatten_semantic_data
from document_engine.semantic.grounding import (
    EvidenceGrounder,
    GroundedSemanticCandidate,
    GroundingMethod,
    GroundingStatus,
    SemanticGroundingReport,
)
from document_engine.semantic.schema_registry import (
    SemanticSchemaSpec,
    get_semantic_schema,
    supports_semantic_schema,
)

__all__ = [
    "EvidenceGrounder",
    "GroundedSemanticCandidate",
    "GroundingMethod",
    "GroundingStatus",
    "SemanticCandidate",
    "SemanticCandidateStatus",
    "SemanticEvidenceHint",
    "SemanticExtractionPolicy",
    "SemanticExtractionRequest",
    "SemanticExtractionResult",
    "SemanticExtractor",
    "SemanticGroundingReport",
    "SemanticSchemaSpec",
    "flatten_semantic_data",
    "get_semantic_schema",
    "supports_semantic_schema",
]
