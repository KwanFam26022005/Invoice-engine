"""Phase 9F.2B.6 fallback acceptance/freeze contract.

This module freezes routing acceptance separately from deterministic fallback
quality. It never upgrades Path B semantic quality, never authorizes holdout
execution, and consumes only privacy-safe Phase 9F verification/observation data.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Mapping

from pydantic import BaseModel, Field

from document_engine.evaluation.phase9f import (
    Phase9EvaluationPath,
    Phase9FDocumentObservation,
)
from document_engine.evaluation.phase9f_fallback_verification import (
    Phase9FPathBFallbackVerification,
)


class FallbackQualityDisposition(str, Enum):
    VALIDATION_ACCEPTED = "VALIDATION_ACCEPTED"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    NOT_ESTABLISHED = "NOT_ESTABLISHED"


class Phase9FPathBFallbackAcceptance(BaseModel):
    """Privacy-safe frozen acceptance result for the Path B -> Path A fallback."""

    phase: str = "9F.2B.6"
    alias: str
    routing_accepted: bool
    fallback_execution_accepted: bool
    fallback_quality_disposition: FallbackQualityDisposition
    fallback_quality_accepted: bool
    semantic_path_b_quality_evaluable: bool = False
    semantic_path_b_quality_accepted: bool = False
    holdout_authorized: bool = False
    generalization_claim_authorized: bool = False

    runtime_verdict: str
    reason_code: str
    selected_path: Phase9EvaluationPath
    fallback_path: Phase9EvaluationPath
    path_b_inference_executed: bool
    path_a_executed: bool
    fallback_verified: bool

    predicted_family: str
    family_match: bool | None = None
    confirmed_field_count: int = Field(ge=0)
    predicted_field_count: int = Field(ge=0)
    normalized_match_count: int = Field(ge=0)
    normalized_match_rate: float | None = Field(default=None, ge=0.0, le=1.0)
    validation_pass: bool | None = None
    review_required: bool | None = None
    selected_parser: str
    private_values_persisted: bool = False


def _quality_disposition(observation: Phase9FDocumentObservation) -> FallbackQualityDisposition:
    if observation.review_required is True or observation.validation_pass is False:
        return FallbackQualityDisposition.REVIEW_REQUIRED
    if observation.validation_pass is True and observation.review_required is False:
        return FallbackQualityDisposition.VALIDATION_ACCEPTED
    return FallbackQualityDisposition.NOT_ESTABLISHED


def assess_phase9f_path_b_fallback_acceptance(
    *,
    verification: Phase9FPathBFallbackVerification,
    observation: Phase9FDocumentObservation,
    path_a_metadata: Mapping[str, Any],
) -> Phase9FPathBFallbackAcceptance:
    """Freeze routing acceptance without converting fallback quality into a semantic claim."""

    routing_accepted = all(
        (
            verification.selected_path == Phase9EvaluationPath.A_DETERMINISTIC,
            verification.fallback_path == Phase9EvaluationPath.A_DETERMINISTIC,
            verification.path_b_inference_executed is False,
            verification.path_a_executed is True,
            verification.fallback_verified is True,
            observation.path == Phase9EvaluationPath.A_DETERMINISTIC,
            observation.alias == verification.alias,
        )
    )
    if not routing_accepted:
        raise ValueError("PHASE_9F2B6_ROUTING_ACCEPTANCE_FAILED")

    allowed_metadata_keys = {
        "selected_parser",
        "validation_status",
        "evidence_coverage",
        "missing_prediction_count",
        "wrong_value_count",
        "evidence_supported_count",
    }
    if set(path_a_metadata) - allowed_metadata_keys:
        raise ValueError("PHASE_9F2B6_METADATA_CONTAINS_UNEXPECTED_FIELDS")

    selected_parser = str(path_a_metadata.get("selected_parser") or "")
    if not selected_parser:
        raise ValueError("PHASE_9F2B6_SELECTED_PARSER_MISSING")

    disposition = _quality_disposition(observation)
    normalized_rate = None
    if observation.confirmed_field_count > 0:
        normalized_rate = observation.normalized_match_count / observation.confirmed_field_count

    return Phase9FPathBFallbackAcceptance(
        alias=verification.alias,
        routing_accepted=True,
        fallback_execution_accepted=True,
        fallback_quality_disposition=disposition,
        fallback_quality_accepted=disposition == FallbackQualityDisposition.VALIDATION_ACCEPTED,
        runtime_verdict=verification.runtime_verdict,
        reason_code=verification.reason_code,
        selected_path=verification.selected_path,
        fallback_path=verification.fallback_path,
        path_b_inference_executed=verification.path_b_inference_executed,
        path_a_executed=verification.path_a_executed,
        fallback_verified=verification.fallback_verified,
        predicted_family=observation.predicted_family.value,
        family_match=observation.family_match,
        confirmed_field_count=observation.confirmed_field_count,
        predicted_field_count=observation.predicted_field_count,
        normalized_match_count=observation.normalized_match_count,
        normalized_match_rate=normalized_rate,
        validation_pass=observation.validation_pass,
        review_required=observation.review_required,
        selected_parser=selected_parser,
        private_values_persisted=False,
    )
