from pathlib import Path

from document_engine.evaluation.phase9f import Phase9EvaluationPath
from document_engine.evaluation.phase9f_runtime_policy import (
    PathBRuntimePurpose,
    PathBRuntimeVerdict,
    Phase9FPathBRuntimePolicyConfig,
    decide_path_b_runtime,
    evidence_from_healthcheck,
    select_path_for_runtime,
)


def _healthcheck(*, device: str, cuda: bool = False, success: bool = True):
    return {
        "success": success,
        "runtime_versions": {"torch": "test"},
        "health_data": {
            "api_available": success,
            "model_cache_ready": success,
            "offline_runtime_ready": success,
            "resource_ready": success,
            "actual_device": device,
            "cuda_available": cuda,
        },
    }


def test_frozen_cpu_timeout_policy_routes_canary_and_production_to_path_a(tmp_path: Path):
    policy_path = tmp_path / "policy.yaml"
    policy_path.write_text(
        """policy_version: '1.0'
fallback_path: a_deterministic
cpu_canary_allowed: false
cpu_production_allowed: false
cpu_timeout_budgets_seconds: [180.0, 600.0]
cpu_blocking_stage: extraction_started
cuda_canary_allowed: true
cuda_production_requires_acceptance: true
semantic_canary_accepted: false
""",
        encoding="utf-8",
    )
    policy = Phase9FPathBRuntimePolicyConfig.load_yaml(policy_path)
    evidence = evidence_from_healthcheck(
        _healthcheck(device="cpu"),
        timed_out_budgets_seconds=policy.cpu_timeout_budgets_seconds,
        last_timeout_stage=policy.cpu_blocking_stage,
    )

    decision = decide_path_b_runtime(evidence, policy)

    assert decision.verdict == PathBRuntimeVerdict.CPU_EXECUTION_SUITABILITY_BLOCKED
    assert decision.reason_code == "CPU_EXTRACTION_TIMEOUT_CONFIRMED"
    assert decision.semantic_quality_evaluable is False
    assert select_path_for_runtime(decision, PathBRuntimePurpose.CANARY) == Phase9EvaluationPath.A_DETERMINISTIC
    assert select_path_for_runtime(decision, PathBRuntimePurpose.PRODUCTION) == Phase9EvaluationPath.A_DETERMINISTIC


def test_cuda_is_canary_only_until_acceptance():
    policy = Phase9FPathBRuntimePolicyConfig()
    evidence = evidence_from_healthcheck(_healthcheck(device="cuda", cuda=True))

    decision = decide_path_b_runtime(evidence, policy)

    assert decision.verdict == PathBRuntimeVerdict.ACCELERATOR_CANARY_REQUIRED
    assert decision.canary_allowed is True
    assert decision.production_allowed is False
    assert decision.semantic_quality_evaluable is True
    assert select_path_for_runtime(decision, PathBRuntimePurpose.CANARY) == Phase9EvaluationPath.B_DOCLING_SEMANTIC
    assert select_path_for_runtime(decision, PathBRuntimePurpose.PRODUCTION) == Phase9EvaluationPath.A_DETERMINISTIC


def test_cuda_accepted_allows_production_path_b():
    policy = Phase9FPathBRuntimePolicyConfig(semantic_canary_accepted=True)
    evidence = evidence_from_healthcheck(_healthcheck(device="cuda", cuda=True))

    decision = decide_path_b_runtime(evidence, policy)

    assert decision.verdict == PathBRuntimeVerdict.ACCELERATOR_ACCEPTED
    assert decision.production_allowed is True
    assert select_path_for_runtime(decision, PathBRuntimePurpose.PRODUCTION) == Phase9EvaluationPath.B_DOCLING_SEMANTIC


def test_unready_runtime_falls_back_without_semantic_quality_claim():
    policy = Phase9FPathBRuntimePolicyConfig()
    evidence = evidence_from_healthcheck(_healthcheck(device="cpu", success=False))

    decision = decide_path_b_runtime(evidence, policy)

    assert decision.verdict == PathBRuntimeVerdict.RUNTIME_NOT_READY
    assert decision.canary_allowed is False
    assert decision.production_allowed is False
    assert decision.semantic_quality_evaluable is False
    assert select_path_for_runtime(decision, PathBRuntimePurpose.PRODUCTION) == Phase9EvaluationPath.A_DETERMINISTIC
