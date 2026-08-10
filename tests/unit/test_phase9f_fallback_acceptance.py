from pathlib import Path

import pytest

from document_engine.core.models import DocumentFamilyType
from document_engine.evaluation.phase9_contract import EvaluationCohort
from document_engine.evaluation.phase9f import (
    Phase9EvaluationPath,
    Phase9FDocumentObservation,
)
from document_engine.evaluation.phase9f_fallback_acceptance import (
    FallbackQualityDisposition,
    Phase9FPathBFallbackAcceptanceFreeze,
    assess_phase9f_path_b_fallback_acceptance,
)
from document_engine.evaluation.phase9f_fallback_verification import (
    Phase9FPathBFallbackVerification,
)
from document_engine.evaluation.phase9f_runtime_policy import PathBRuntimePurpose


def _verification() -> Phase9FPathBFallbackVerification:
    return Phase9FPathBFallbackVerification(
        alias="current_tax_001",
        purpose=PathBRuntimePurpose.CANARY,
        runtime_verdict="CPU_EXECUTION_SUITABILITY_BLOCKED",
        reason_code="CPU_EXTRACTION_TIMEOUT_CONFIRMED",
        selected_path=Phase9EvaluationPath.A_DETERMINISTIC,
        fallback_path=Phase9EvaluationPath.A_DETERMINISTIC,
        path_b_inference_executed=False,
        path_a_executed=True,
        fallback_verified=True,
        private_values_returned=False,
    )


def _observation(*, validation_pass=False, review_required=True):
    return Phase9FDocumentObservation(
        alias="current_tax_001",
        cohort=EvaluationCohort.CURRENT_PILOT,
        path=Phase9EvaluationPath.A_DETERMINISTIC,
        predicted_family=DocumentFamilyType.TAX_WITHHOLDING_CERTIFICATE,
        family_match=True,
        confirmed_field_count=13,
        predicted_field_count=7,
        exact_match_count=2,
        normalized_match_count=2,
        false_positive_count=5,
        grounded_prediction_count=7,
        grounded_correct_count=2,
        validation_pass=validation_pass,
        review_required=review_required,
    )


def _metadata():
    return {
        "selected_parser": "pymupdf_native",
        "validation_status": "review_required",
        "evidence_coverage": 1.0,
        "missing_prediction_count": 6,
        "wrong_value_count": 5,
        "evidence_supported_count": 7,
    }


def test_current_fallback_routes_accept_but_quality_requires_review(tmp_path: Path):
    acceptance = assess_phase9f_path_b_fallback_acceptance(
        verification=_verification(),
        observation=_observation(),
        path_a_metadata=_metadata(),
    )

    assert acceptance.routing_accepted is True
    assert acceptance.fallback_execution_accepted is True
    assert acceptance.fallback_quality_disposition == FallbackQualityDisposition.REVIEW_REQUIRED
    assert acceptance.fallback_quality_accepted is False
    assert acceptance.normalized_match_rate == pytest.approx(2 / 13)
    assert acceptance.semantic_path_b_quality_evaluable is False
    assert acceptance.semantic_path_b_quality_accepted is False
    assert acceptance.holdout_authorized is False
    assert acceptance.generalization_claim_authorized is False

    freeze_path = tmp_path / "freeze.yaml"
    freeze_path.write_text(
        """acceptance_version: '1.0'
source_phase: '9F.2B.5'
alias: current_tax_001
runtime_verdict: CPU_EXECUTION_SUITABILITY_BLOCKED
reason_code: CPU_EXTRACTION_TIMEOUT_CONFIRMED
selected_path: a_deterministic
fallback_path: a_deterministic
path_b_inference_executed: false
path_a_executed: true
fallback_verified: true
routing_accepted: true
fallback_execution_accepted: true
predicted_family: tax_withholding_certificate
family_match: true
confirmed_field_count: 13
predicted_field_count: 7
normalized_match_count: 2
validation_pass: false
review_required: true
selected_parser: pymupdf_native
fallback_quality_disposition: REVIEW_REQUIRED
fallback_quality_accepted: false
semantic_path_b_quality_evaluable: false
semantic_path_b_quality_accepted: false
holdout_authorized: false
generalization_claim_authorized: false
private_values_persisted: false
""",
        encoding="utf-8",
    )
    freeze = Phase9FPathBFallbackAcceptanceFreeze.load_yaml(freeze_path)
    freeze.validate_acceptance(acceptance)


def test_freeze_mismatch_is_rejected(tmp_path: Path):
    acceptance = assess_phase9f_path_b_fallback_acceptance(
        verification=_verification(),
        observation=_observation(),
        path_a_metadata=_metadata(),
    )
    freeze_path = tmp_path / "freeze.yaml"
    freeze_path.write_text(
        """acceptance_version: '1.0'
source_phase: '9F.2B.5'
alias: current_tax_001
runtime_verdict: CPU_EXECUTION_SUITABILITY_BLOCKED
reason_code: CPU_EXTRACTION_TIMEOUT_CONFIRMED
selected_path: a_deterministic
fallback_path: a_deterministic
path_b_inference_executed: false
path_a_executed: true
fallback_verified: true
routing_accepted: true
fallback_execution_accepted: true
predicted_family: tax_withholding_certificate
family_match: true
confirmed_field_count: 13
predicted_field_count: 7
normalized_match_count: 3
validation_pass: false
review_required: true
selected_parser: pymupdf_native
fallback_quality_disposition: REVIEW_REQUIRED
fallback_quality_accepted: false
semantic_path_b_quality_evaluable: false
semantic_path_b_quality_accepted: false
holdout_authorized: false
generalization_claim_authorized: false
private_values_persisted: false
""",
        encoding="utf-8",
    )
    freeze = Phase9FPathBFallbackAcceptanceFreeze.load_yaml(freeze_path)

    with pytest.raises(ValueError, match="PHASE_9F2B6_FREEZE_MISMATCH"):
        freeze.validate_acceptance(acceptance)


def test_validation_accepted_fallback_still_does_not_authorize_holdout():
    observation = _observation(validation_pass=True, review_required=False)
    acceptance = assess_phase9f_path_b_fallback_acceptance(
        verification=_verification(),
        observation=observation,
        path_a_metadata=_metadata(),
    )

    assert acceptance.fallback_quality_disposition == FallbackQualityDisposition.VALIDATION_ACCEPTED
    assert acceptance.fallback_quality_accepted is True
    assert acceptance.semantic_path_b_quality_accepted is False
    assert acceptance.holdout_authorized is False
    assert acceptance.generalization_claim_authorized is False
