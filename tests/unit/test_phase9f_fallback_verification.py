from pathlib import Path

import pytest

from document_engine.core.models import DocumentFamilyType
from document_engine.evaluation.phase9_contract import EvaluationCohort
from document_engine.evaluation.phase9f import (
    Phase9EvaluationPath,
    Phase9FDocumentObservation,
)
from document_engine.evaluation.phase9f_fallback_verification import (
    verify_phase9f_path_b_fallback,
)
from document_engine.evaluation.phase9f_runtime_policy import (
    PathBRuntimePurpose,
    Phase9FPathBRuntimePolicyConfig,
)


def _healthcheck(*, device: str, cuda: bool = False):
    return {
        "success": True,
        "runtime_versions": {"torch": "test"},
        "health_data": {
            "api_available": True,
            "model_cache_ready": True,
            "offline_runtime_ready": True,
            "resource_ready": True,
            "actual_device": device,
            "cuda_available": cuda,
        },
    }


def _path_a_observation(alias: str) -> Phase9FDocumentObservation:
    return Phase9FDocumentObservation(
        alias=alias,
        cohort=EvaluationCohort.CURRENT_PILOT,
        path=Phase9EvaluationPath.A_DETERMINISTIC,
        predicted_family=DocumentFamilyType.TAX_WITHHOLDING_CERTIFICATE,
        family_match=True,
        confirmed_field_count=2,
        predicted_field_count=2,
        exact_match_count=2,
        normalized_match_count=2,
        false_positive_count=0,
        grounded_prediction_count=2,
        grounded_correct_count=2,
        unsupported_prediction_count=0,
        abstained_field_count=0,
        hallucination_count=0,
        completeness_score=1.0,
        validation_pass=True,
        review_required=False,
        runtime_seconds=0.1,
        peak_rss_mb=50.0,
    )


def _policy() -> Phase9FPathBRuntimePolicyConfig:
    return Phase9FPathBRuntimePolicyConfig(
        fallback_path=Phase9EvaluationPath.A_DETERMINISTIC,
        cpu_canary_allowed=False,
        cpu_production_allowed=False,
        cpu_timeout_budgets_seconds=[180.0, 600.0],
        cpu_blocking_stage="extraction_started",
        cuda_canary_allowed=True,
        cuda_production_requires_acceptance=True,
        semantic_canary_accepted=False,
    )


def test_cpu_blocked_runtime_executes_independent_path_a_fallback(tmp_path: Path):
    calls = []

    def fake_path_a(alias: str, repo_root: Path, manifest_path: str):
        calls.append((alias, repo_root, manifest_path))
        return _path_a_observation(alias), {
            "selected_parser": "pymupdf_native",
            "validation_status": "accepted",
            "evidence_coverage": 1.0,
            "missing_prediction_count": 0,
            "wrong_value_count": 0,
            "evidence_supported_count": 2,
        }

    verification, observation, metadata = verify_phase9f_path_b_fallback(
        alias="current_tax_001",
        healthcheck_response=_healthcheck(device="cpu"),
        policy=_policy(),
        repo_root=tmp_path,
        purpose=PathBRuntimePurpose.CANARY,
        path_a_executor=fake_path_a,
    )

    assert len(calls) == 1
    assert verification.runtime_verdict == "CPU_EXECUTION_SUITABILITY_BLOCKED"
    assert verification.reason_code == "CPU_EXTRACTION_TIMEOUT_CONFIRMED"
    assert verification.selected_path == Phase9EvaluationPath.A_DETERMINISTIC
    assert verification.fallback_path == Phase9EvaluationPath.A_DETERMINISTIC
    assert verification.path_b_inference_executed is False
    assert verification.path_a_executed is True
    assert verification.fallback_verified is True
    assert verification.private_values_returned is False
    assert observation.path == Phase9EvaluationPath.A_DETERMINISTIC
    assert metadata["selected_parser"] == "pymupdf_native"


def test_cuda_canary_is_not_misreported_as_fallback(tmp_path: Path):
    called = False

    def fake_path_a(alias: str, repo_root: Path, manifest_path: str):
        nonlocal called
        called = True
        return _path_a_observation(alias), {}

    with pytest.raises(RuntimeError, match="PATH_B_FALLBACK_NOT_SELECTED"):
        verify_phase9f_path_b_fallback(
            alias="current_tax_001",
            healthcheck_response=_healthcheck(device="cuda", cuda=True),
            policy=_policy(),
            repo_root=tmp_path,
            purpose=PathBRuntimePurpose.CANARY,
            path_a_executor=fake_path_a,
        )

    assert called is False


def test_fallback_rejects_unexpected_metadata_fields(tmp_path: Path):
    def unsafe_path_a(alias: str, repo_root: Path, manifest_path: str):
        return _path_a_observation(alias), {
            "selected_parser": "pymupdf_native",
            "source_path": "private.pdf",
        }

    with pytest.raises(ValueError, match="FALLBACK_METADATA_CONTAINS_UNEXPECTED_FIELDS"):
        verify_phase9f_path_b_fallback(
            alias="current_tax_001",
            healthcheck_response=_healthcheck(device="cpu"),
            policy=_policy(),
            repo_root=tmp_path,
            purpose=PathBRuntimePurpose.CANARY,
            path_a_executor=unsafe_path_a,
        )
