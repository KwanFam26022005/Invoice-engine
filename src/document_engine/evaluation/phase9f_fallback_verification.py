"""Phase 9F.2B.5 fallback/routing verification.

This module verifies that a blocked Path B runtime decision actually routes to
Path A and that the resulting deterministic observation remains a standalone
privacy-safe Phase 9F Path A observation. It never executes Path B inference.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Dict, Mapping, Optional

from pydantic import BaseModel

from document_engine.evaluation.phase9f import (
    Phase9EvaluationPath,
    Phase9FDocumentObservation,
    execute_phase9f_path_a_observation,
)
from document_engine.evaluation.phase9f_runtime_policy import (
    PathBRuntimePurpose,
    Phase9FPathBRuntimePolicyConfig,
    decide_path_b_runtime,
    evidence_from_healthcheck,
    select_path_for_runtime,
)


class Phase9FPathBFallbackVerification(BaseModel):
    """Privacy-safe proof that runtime routing selected and executed Path A."""

    alias: str
    purpose: PathBRuntimePurpose
    runtime_verdict: str
    reason_code: str
    selected_path: Phase9EvaluationPath
    fallback_path: Phase9EvaluationPath
    path_b_inference_executed: bool = False
    path_a_executed: bool
    fallback_verified: bool
    private_values_returned: bool = False


PathAExecutor = Callable[
    [str, Path, str],
    tuple[Phase9FDocumentObservation, Dict[str, Any]],
]


def verify_phase9f_path_b_fallback(
    *,
    alias: str,
    healthcheck_response: Mapping[str, Any],
    policy: Phase9FPathBRuntimePolicyConfig,
    repo_root: Path = Path("."),
    manifest_path: str = "workspace/private/phase9/phase9_manifest.yaml",
    purpose: PathBRuntimePurpose = PathBRuntimePurpose.CANARY,
    path_a_executor: Optional[PathAExecutor] = None,
) -> tuple[
    Phase9FPathBFallbackVerification,
    Phase9FDocumentObservation,
    Dict[str, Any],
]:
    """Verify a policy-selected Path A fallback without invoking semantic inference."""

    evidence = evidence_from_healthcheck(
        healthcheck_response,
        timed_out_budgets_seconds=policy.cpu_timeout_budgets_seconds,
        last_timeout_stage=policy.cpu_blocking_stage,
        semantic_canary_accepted=policy.semantic_canary_accepted,
    )
    decision = decide_path_b_runtime(evidence, policy)
    selected_path = select_path_for_runtime(decision, purpose)

    if selected_path != policy.fallback_path:
        raise RuntimeError("PATH_B_FALLBACK_NOT_SELECTED")
    if selected_path != Phase9EvaluationPath.A_DETERMINISTIC:
        raise RuntimeError("PHASE_9F2B5_REQUIRES_PATH_A_FALLBACK")

    executor = path_a_executor or execute_phase9f_path_a_observation
    observation, metadata = executor(alias, Path(repo_root), manifest_path)

    if observation.path != Phase9EvaluationPath.A_DETERMINISTIC:
        raise ValueError("FALLBACK_EXECUTOR_RETURNED_NON_PATH_A_OBSERVATION")
    if observation.alias != alias:
        raise ValueError("FALLBACK_EXECUTOR_ALIAS_MISMATCH")

    allowed_metadata_keys = {
        "selected_parser",
        "validation_status",
        "evidence_coverage",
        "missing_prediction_count",
        "wrong_value_count",
        "evidence_supported_count",
    }
    unexpected_keys = set(metadata) - allowed_metadata_keys
    if unexpected_keys:
        raise ValueError("FALLBACK_METADATA_CONTAINS_UNEXPECTED_FIELDS")

    verification = Phase9FPathBFallbackVerification(
        alias=alias,
        purpose=purpose,
        runtime_verdict=decision.verdict.value,
        reason_code=decision.reason_code,
        selected_path=selected_path,
        fallback_path=decision.fallback_path,
        path_b_inference_executed=False,
        path_a_executed=True,
        fallback_verified=True,
        private_values_returned=False,
    )
    return verification, observation, metadata
