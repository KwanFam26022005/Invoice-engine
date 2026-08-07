"""Candidate extraction data structure and completeness evaluation."""

from typing import Dict, List, Literal, Optional
from pydantic import BaseModel, Field

from document_engine.schemas.family_schemas import FieldCandidate


FieldStatus = Literal["present", "not_extracted", "missing_in_source", "ambiguous"]


class FamilyCompletenessReport(BaseModel):
    document_family: str
    required_fields: List[str]
    extracted_fields: List[str]
    missing_fields: List[str]
    field_statuses: Dict[str, FieldStatus] = Field(default_factory=dict)
    completeness_score: float = 0.0
    requires_review: bool = False
    review_reasons: List[str] = Field(default_factory=list)

    @classmethod
    def evaluate(
        cls,
        family_name: str,
        required_candidates: List[str],
        field_candidates: Dict[str, FieldCandidate],
        source_text: str = "",
    ) -> "FamilyCompletenessReport":
        extracted = []
        missing = []
        statuses: Dict[str, FieldStatus] = {}
        reasons = []

        for req in required_candidates:
            cand = field_candidates.get(req)
            if cand and cand.value is not None and str(cand.value).strip():
                extracted.append(req)
                statuses[req] = "present"
            else:
                missing.append(req)
                # Check if field keyword exists in source text
                if req in source_text.lower() or req.replace("_", " ") in source_text.lower():
                    statuses[req] = "not_extracted"
                    reasons.append(f"Required candidate '{req}' present in source text but not extracted.")
                else:
                    statuses[req] = "missing_in_source"

        score = len(extracted) / len(required_candidates) if required_candidates else 1.0
        req_review = len(missing) > 0 or score < 0.8

        return cls(
            document_family=family_name,
            required_fields=required_candidates,
            extracted_fields=extracted,
            missing_fields=missing,
            field_statuses=statuses,
            completeness_score=score,
            requires_review=req_review,
            review_reasons=reasons,
        )
