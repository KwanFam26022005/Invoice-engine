"""Phase 9F Path B runtime suitability policy.

The policy is intentionally independent from semantic quality. A runtime can be
healthy enough for a lightweight healthcheck while still being unsuitable for
heavy semantic extraction. The current Phase 9F contract therefore keeps Path B
available as an accelerator-backed canary, but routes CPU production execution to
Path A after the controlled CPU timeout evidence is frozen.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Mapping, Optional

from pydantic import BaseModel, Field

from document_engine.evaluation.phase9f import Phase9EvaluationPath


class PathBRuntimeVerdict(str, Enum):
    RUNTIME_NOT_READY = "RUNTIME_NOT_READY"
    CPU_EXECUTION_SUITABILITY_BLOCKED = "CPU_EXECUTION_SUITABILITY_BLOCKED"
    ACCELERATOR_CANARY_REQUIRED = "ACCELERATOR_CANARY_REQUIRED"
    ACCELERATOR_ACCEPTED = "ACCELERATOR_ACCEPTED"


class Phase9FPathBRuntimeEvidence(BaseModel):
    """Privacy-safe runtime evidence; no document or extracted values are allowed."""

    healthcheck_success: bool
    api_available: bool
    model_cache_ready: bool
    offline_runtime_ready: bool
    resource_ready: bool
    actual_device: str
    cuda_available: bool = False
    torch_version: Optional[str] = None
    timed_out_budgets_seconds: list[float] = Field(default_factory=list)
    last_timeout_stage: Optional[str] = None
    semantic_canary_accepted: bool = False

    @property
    def runtime_ready(self) -> bool:
        return all(
            (
                self.healthcheck_success,
                self.api_available,
                self.model_cache_ready,
                self.offline_runtime_ready,
                self.resource_ready,
            )
        )


class Phase9FPathBRuntimeDecision(BaseModel):
    verdict: PathBRuntimeVerdict
    healthcheck_allowed: bool
    canary_allowed: bool
    production_allowed: bool
    semantic_quality_evaluable: bool
    fallback_path: Phase9EvaluationPath = Phase9EvaluationPath.A_DETERMINISTIC
    reason_code: str


def evidence_from_healthcheck(
    response: Mapping[str, Any],
    *,
    timed_out_budgets_seconds: Optional[list[float]] = None,
    last_timeout_stage: Optional[str] = None,
    semantic_canary_accepted: bool = False,
) -> Phase9FPathBRuntimeEvidence:
    """Reduce a worker healthcheck to a privacy-safe runtime evidence record."""

    health = response.get("health_data") or {}
    runtime_versions = response.get("runtime_versions") or {}
    return Phase9FPathBRuntimeEvidence(
        healthcheck_success=bool(response.get("success")),
        api_available=bool(health.get("api_available")),
        model_cache_ready=bool(health.get("model_cache_ready")),
        offline_runtime_ready=bool(health.get("offline_runtime_ready")),
        resource_ready=bool(health.get("resource_ready")),
        actual_device=str(health.get("actual_device") or "unknown").lower(),
        cuda_available=bool(health.get("cuda_available")),
        torch_version=(str(runtime_versions["torch"]) if runtime_versions.get("torch") else None),
        timed_out_budgets_seconds=list(timed_out_budgets_seconds or []),
        last_timeout_stage=last_timeout_stage,
        semantic_canary_accepted=semantic_canary_accepted,
    )


def decide_path_b_runtime(evidence: Phase9FPathBRuntimeEvidence) -> Phase9FPathBRuntimeDecision:
    """Return the frozen Phase 9F runtime decision without judging model quality."""

    if not evidence.runtime_ready:
        return Phase9FPathBRuntimeDecision(
            verdict=PathBRuntimeVerdict.RUNTIME_NOT_READY,
            healthcheck_allowed=True,
            canary_allowed=False,
            production_allowed=False,
            semantic_quality_evaluable=False,
            reason_code="PATH_B_RUNTIME_PREFLIGHT_FAILED",
        )

    if evidence.actual_device == "cpu":
        long_timeout_seen = any(budget >= 600.0 for budget in evidence.timed_out_budgets_seconds)
        extraction_blocked = evidence.last_timeout_stage == "extraction_started"
        reason = (
            "CPU_EXTRACTION_TIMEOUT_CONFIRMED"
            if long_timeout_seen and extraction_blocked
            else "CPU_ACCELERATOR_POLICY"
        )
        return Phase9FPathBRuntimeDecision(
            verdict=PathBRuntimeVerdict.CPU_EXECUTION_SUITABILITY_BLOCKED,
            healthcheck_allowed=True,
            canary_allowed=False,
            production_allowed=False,
            semantic_quality_evaluable=False,
            reason_code=reason,
        )

    if evidence.actual_device == "cuda" and evidence.cuda_available:
        if evidence.semantic_canary_accepted:
            return Phase9FPathBRuntimeDecision(
                verdict=PathBRuntimeVerdict.ACCELERATOR_ACCEPTED,
                healthcheck_allowed=True,
                canary_allowed=True,
                production_allowed=True,
                semantic_quality_evaluable=True,
                reason_code="CUDA_CANARY_ACCEPTED",
            )
        return Phase9FPathBRuntimeDecision(
            verdict=PathBRuntimeVerdict.ACCELERATOR_CANARY_REQUIRED,
            healthcheck_allowed=True,
            canary_allowed=True,
            production_allowed=False,
            semantic_quality_evaluable=True,
            reason_code="CUDA_CANARY_NOT_YET_ACCEPTED",
        )

    return Phase9FPathBRuntimeDecision(
        verdict=PathBRuntimeVerdict.RUNTIME_NOT_READY,
        healthcheck_allowed=True,
        canary_allowed=False,
        production_allowed=False,
        semantic_quality_evaluable=False,
        reason_code="UNSUPPORTED_PATH_B_DEVICE",
    )
