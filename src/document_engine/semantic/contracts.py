"""Engine-agnostic contracts for schema-conditioned semantic extraction.

Semantic extractors produce candidates only. They do not mutate DocumentIR,
validate financial truth, or automatically become canonical business objects.
Evidence grounding and deterministic validation are separate downstream stages.
"""

from enum import Enum
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable

from pydantic import BaseModel, Field, model_validator

from document_engine.core.models import DocumentFamilyType
from document_engine.ir.models import DocumentIR


class SemanticCandidateStatus(str, Enum):
    PROPOSED = "proposed"
    ABSTAINED = "abstained"
    UNSUPPORTED = "unsupported"


class SemanticEvidenceHint(BaseModel):
    page_number: Optional[int] = Field(default=None, ge=1)
    block_id: Optional[str] = None
    table_id: Optional[str] = None
    cell_id: Optional[str] = None
    bbox: Optional[List[float]] = None


class SemanticCandidate(BaseModel):
    field_path: str = Field(min_length=1)
    value: Optional[Any] = None
    raw_value: Optional[Any] = None
    confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    source_method: str = Field(min_length=1)
    status: SemanticCandidateStatus = SemanticCandidateStatus.PROPOSED
    evidence_hints: List[SemanticEvidenceHint] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_candidate_state(self) -> "SemanticCandidate":
        if self.status == SemanticCandidateStatus.ABSTAINED and self.value is not None:
            raise ValueError("Abstained semantic candidates must not contain a value.")
        if self.status == SemanticCandidateStatus.PROPOSED and self.value is None:
            raise ValueError("Proposed semantic candidates must contain a value.")
        return self


class SemanticExtractionPolicy(BaseModel):
    local_runtime_only: bool = True
    allow_network: bool = False
    abstain_on_uncertain: bool = True
    minimum_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    max_candidates_per_field: int = Field(default=1, ge=1)

    @model_validator(mode="after")
    def validate_local_runtime(self) -> "SemanticExtractionPolicy":
        if self.local_runtime_only and self.allow_network:
            raise ValueError("Local semantic extraction runtime cannot allow network access.")
        return self


class SemanticExtractionRequest(BaseModel):
    document_id: str = Field(min_length=1)
    family: DocumentFamilyType
    target_schema_name: str = Field(min_length=1)
    document_ir: DocumentIR
    page_image_refs: List[str] = Field(default_factory=list)
    policy: SemanticExtractionPolicy = Field(default_factory=SemanticExtractionPolicy)

    @model_validator(mode="after")
    def validate_document_identity(self) -> "SemanticExtractionRequest":
        if self.document_id != self.document_ir.document_id:
            raise ValueError(
                "Semantic request document_id must match DocumentIR.document_id."
            )
        return self


class SemanticExtractionResult(BaseModel):
    extractor_id: str = Field(min_length=1)
    extractor_version: str = Field(default="unknown", min_length=1)
    document_id: str = Field(min_length=1)
    family: DocumentFamilyType
    success: bool = True
    candidates: List[SemanticCandidate] = Field(default_factory=list)
    abstained_fields: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    error_code: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)

    def candidates_by_field(self) -> Dict[str, List[SemanticCandidate]]:
        grouped: Dict[str, List[SemanticCandidate]] = {}
        for candidate in self.candidates:
            grouped.setdefault(candidate.field_path, []).append(candidate)
        return grouped


@runtime_checkable
class SemanticExtractor(Protocol):
    extractor_id: str

    def supports(
        self,
        family: DocumentFamilyType,
        target_schema_name: str,
        document_ir: DocumentIR,
    ) -> bool:
        ...

    def extract(self, request: SemanticExtractionRequest) -> SemanticExtractionResult:
        ...
