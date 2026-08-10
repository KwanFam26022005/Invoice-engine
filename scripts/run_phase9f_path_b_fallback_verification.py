"""Manual runner for Phase 9F.2B.5 Path B -> Path A fallback verification."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from document_engine.evaluation.phase9f_fallback_verification import (
    verify_phase9f_path_b_fallback,
)
from document_engine.evaluation.phase9f_runtime_policy import (
    PathBRuntimePurpose,
    Phase9FPathBRuntimePolicyConfig,
)
from document_engine.semantic.extractors.docling_semantic import DoclingSemanticExtractor


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Verify that frozen Path B runtime policy routes a blocked runtime to "
            "an independent deterministic Path A observation."
        )
    )
    parser.add_argument("--alias", default="current_tax_001")
    parser.add_argument(
        "--manifest",
        default="workspace/private/phase9/phase9_manifest.yaml",
    )
    parser.add_argument(
        "--runtime-policy",
        default="configs/evaluation/phase9f_path_b_runtime_policy.yaml",
    )
    parser.add_argument(
        "--purpose",
        choices=[item.value for item in PathBRuntimePurpose],
        default=PathBRuntimePurpose.CANARY.value,
    )
    parser.add_argument(
        "--output",
        default="workspace/phase9f/path_b_fallback_verification.json",
    )
    return parser


def _resolve_repo_file(root: Path, relative_path: str, label: str) -> Path:
    resolved = (root / relative_path).resolve()
    if resolved != root and root not in resolved.parents:
        raise ValueError(f"{label} escaped repository root.")
    if not resolved.is_file():
        raise FileNotFoundError(f"{label} is not available.")
    return resolved


def main() -> int:
    args = _parser().parse_args()
    repo_root = Path.cwd().resolve()

    try:
        policy_path = _resolve_repo_file(repo_root, args.runtime_policy, "Runtime policy")
        policy = Phase9FPathBRuntimePolicyConfig.load_yaml(policy_path)
        healthcheck = DoclingSemanticExtractor().healthcheck(allow_model_download=False)
        verification, observation, path_a_metadata = verify_phase9f_path_b_fallback(
            alias=args.alias,
            healthcheck_response=healthcheck.model_dump(mode="json"),
            policy=policy,
            repo_root=repo_root,
            manifest_path=args.manifest,
            purpose=PathBRuntimePurpose(args.purpose),
        )
    except Exception as exc:
        print(f"PHASE_9F2B5_FALLBACK_VERIFICATION_FAILED:{type(exc).__name__}")
        print(f"reason={str(exc)}")
        print("path_b_inference_executed=false")
        print("private_values_persisted=false")
        return 2

    payload = {
        "phase": "9F.2B.5",
        "verification": verification.model_dump(mode="json"),
        "path_a_observation": observation.model_dump(mode="json"),
        "path_a_metadata": path_a_metadata,
        "private_values_persisted": False,
    }
    output_path = (repo_root / args.output).resolve()
    if output_path != repo_root and repo_root not in output_path.parents:
        print("PHASE_9F2B5_FALLBACK_VERIFICATION_FAILED:ValueError")
        print("reason=Output path escaped repository root.")
        print("path_b_inference_executed=false")
        print("private_values_persisted=false")
        return 2
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    print("PHASE_9F2B5_FALLBACK_VERIFICATION")
    print(f"runtime_verdict={verification.runtime_verdict}")
    print(f"reason_code={verification.reason_code}")
    print(f"purpose={verification.purpose.value}")
    print(f"selected_path={verification.selected_path.value}")
    print(f"fallback_path={verification.fallback_path.value}")
    print(f"path_b_inference_executed={str(verification.path_b_inference_executed).lower()}")
    print(f"path_a_executed={str(verification.path_a_executed).lower()}")
    print(f"fallback_verified={str(verification.fallback_verified).lower()}")
    print(f"path_a_predicted_family={observation.predicted_family.value}")
    print(f"path_a_family_match={observation.family_match}")
    print(f"path_a_confirmed_field_count={observation.confirmed_field_count}")
    print(f"path_a_predicted_field_count={observation.predicted_field_count}")
    print(f"path_a_normalized_match_count={observation.normalized_match_count}")
    print(f"path_a_validation_pass={observation.validation_pass}")
    print(f"path_a_review_required={observation.review_required}")
    print(f"path_a_runtime_seconds={observation.runtime_seconds}")
    print(f"path_a_selected_parser={path_a_metadata['selected_parser']}")
    print(f"output={args.output}")
    print("private_values_persisted=false")
    return 0


if __name__ == "__main__":
    sys.exit(main())
