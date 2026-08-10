"""Manual-terminal runner for one Phase 9F.2B Docling semantic dry run."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from document_engine.evaluation.phase9f import Phase9EvaluationPath
from document_engine.evaluation.phase9f_path_b import (
    execute_phase9f_path_b_observation,
    probe_phase9f_path_b_alias,
)
from document_engine.evaluation.phase9f_runtime_policy import (
    PathBRuntimePurpose,
    Phase9FPathBRuntimePolicyConfig,
    decide_path_b_runtime,
    evidence_from_healthcheck,
    select_path_for_runtime,
)
from document_engine.runtime.worker_errors import WorkerTimeoutError


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Probe or manually execute one CURRENT_PILOT Phase 9F Path B dry run."
    )
    parser.add_argument("--alias", default="current_tax_001")
    parser.add_argument(
        "--manifest",
        default="workspace/private/phase9/phase9_manifest.yaml",
    )
    parser.add_argument(
        "--output",
        default="workspace/phase9f/path_b_current_pilot_dry_run.json",
    )
    parser.add_argument(
        "--runtime-policy",
        default="configs/evaluation/phase9f_path_b_runtime_policy.yaml",
        help="Tracked Path B runtime suitability policy.",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=float,
        default=180.0,
        help="Semantic worker execution budget in seconds (default: 180).",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Explicitly permit the real local Docling/NuExtract model call when runtime policy allows it.",
    )
    return parser


def _print_eligibility(report) -> None:
    data = report.model_dump(mode="json")
    print("PHASE_9F2B_ELIGIBILITY")
    for key in (
        "alias",
        "page_count",
        "block_count",
        "table_count",
        "full_text_char_count",
        "selected_parser",
        "predicted_family",
        "classifier_confidence",
        "semantic_schema_supported",
        "eligible",
    ):
        print(f"{key}={data[key]}")


def _load_runtime_policy(repo_root: Path, relative_path: str) -> Phase9FPathBRuntimePolicyConfig:
    policy_path = (repo_root / relative_path).resolve()
    if policy_path != repo_root and repo_root not in policy_path.parents:
        raise ValueError("Phase 9F runtime policy escaped repository root.")
    if not policy_path.is_file():
        raise FileNotFoundError("Phase 9F Path B runtime policy is unavailable.")
    return Phase9FPathBRuntimePolicyConfig.load_yaml(policy_path)


def _evaluate_runtime_policy(repo_root: Path, args):
    policy = _load_runtime_policy(repo_root, args.runtime_policy)

    # Healthcheck is structure/runtime-only and does not load the semantic model.
    from document_engine.semantic.extractors.docling_semantic import DoclingSemanticExtractor

    health_timeout = max(30.0, min(float(args.timeout_seconds), 60.0))
    response = DoclingSemanticExtractor(timeout=health_timeout).healthcheck()
    response_dict = response.model_dump(mode="json")
    evidence = evidence_from_healthcheck(
        response_dict,
        timed_out_budgets_seconds=policy.cpu_timeout_budgets_seconds,
        last_timeout_stage=policy.cpu_blocking_stage,
        semantic_canary_accepted=policy.semantic_canary_accepted,
    )
    decision = decide_path_b_runtime(evidence, policy)
    selected_path = select_path_for_runtime(decision, PathBRuntimePurpose.CANARY)
    return evidence, decision, selected_path


def main() -> int:
    args = _parser().parse_args()
    if args.timeout_seconds <= 0:
        print("PHASE_9F2B_INVALID_TIMEOUT")
        return 2

    repo_root = Path.cwd().resolve()

    try:
        eligibility = probe_phase9f_path_b_alias(
            alias=args.alias,
            repo_root=repo_root,
            manifest_path=args.manifest,
        )
    except Exception as exc:
        print(f"PHASE_9F2B_PROBE_FAILED:{type(exc).__name__}")
        return 2

    _print_eligibility(eligibility)
    if not eligibility.eligible:
        print("PHASE_9F2B_NOT_ELIGIBLE")
        return 3

    if not args.execute:
        print(f"semantic_timeout_seconds={args.timeout_seconds}")
        print("model_loaded=false")
        print("inference_executed=false")
        print("private_values_persisted=false")
        print("MANUAL_TERMINAL_TASK_REQUIRED")
        print(
            "Run again from the base environment with --execute after confirming "
            "offline model artifacts are ready. Runtime policy will be checked first."
        )
        return 0

    try:
        evidence, runtime_decision, selected_path = _evaluate_runtime_policy(repo_root, args)
    except Exception as exc:
        print(f"PHASE_9F2B_RUNTIME_POLICY_FAILED:{type(exc).__name__}")
        print("private_values_persisted=false")
        return 6

    print("PHASE_9F2B_RUNTIME_POLICY")
    print(f"runtime_verdict={runtime_decision.verdict.value}")
    print(f"reason_code={runtime_decision.reason_code}")
    print(f"actual_device={evidence.actual_device}")
    print(f"cuda_available={evidence.cuda_available}")
    print(f"canary_allowed={runtime_decision.canary_allowed}")
    print(f"production_allowed={runtime_decision.production_allowed}")
    print(f"semantic_quality_evaluable={runtime_decision.semantic_quality_evaluable}")
    print(f"selected_path={selected_path.value}")
    print(f"fallback_path={runtime_decision.fallback_path.value}")

    if selected_path != Phase9EvaluationPath.B_DOCLING_SEMANTIC:
        print("PHASE_9F2B_RUNTIME_BLOCKED")
        print("model_loaded=false")
        print("inference_executed=false")
        print("private_values_persisted=false")
        return 6

    try:
        observation, metadata = execute_phase9f_path_b_observation(
            alias=args.alias,
            repo_root=repo_root,
            manifest_path=args.manifest,
            allow_heavy_execution=True,
            semantic_timeout_seconds=args.timeout_seconds,
        )
    except WorkerTimeoutError as exc:
        print("PHASE_9F2B_DRY_RUN_FAILED:WorkerTimeoutError")
        print(f"semantic_timeout_seconds={args.timeout_seconds}")
        print(f"timeout_diagnostic={exc}")
        print("private_values_persisted=false")
        return 4
    except Exception as exc:
        print(f"PHASE_9F2B_DRY_RUN_FAILED:{type(exc).__name__}")
        print(f"semantic_timeout_seconds={args.timeout_seconds}")
        return 4

    metadata["runtime_verdict"] = runtime_decision.verdict.value
    metadata["runtime_reason_code"] = runtime_decision.reason_code
    metadata["runtime_actual_device"] = evidence.actual_device
    metadata["runtime_canary_allowed"] = runtime_decision.canary_allowed
    metadata["runtime_production_allowed"] = runtime_decision.production_allowed

    payload = {
        "phase": "9F.2B",
        "alias": args.alias,
        "observation": observation.model_dump(mode="json"),
        "metadata": metadata,
        "private_values_persisted": False,
    }
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    print("PHASE_9F2B_DRY_RUN_EXECUTED")
    print(f"semantic_success={metadata['semantic_success']}")
    print(f"semantic_error_code={metadata['semantic_error_code']}")
    print(f"predicted_family={metadata['predicted_family']}")
    print(f"candidate_count={metadata['candidate_count']}")
    print(f"grounded_count={metadata['grounded_count']}")
    print(f"unsupported_count={metadata['unsupported_count']}")
    print(f"abstained_count={metadata['abstained_count']}")
    print(f"semantic_timeout_seconds={metadata['semantic_timeout_seconds']}")
    print(f"output={output_path.as_posix()}")
    print("private_values_persisted=false")
    return 0 if metadata["semantic_success"] else 5


if __name__ == "__main__":
    sys.exit(main())
