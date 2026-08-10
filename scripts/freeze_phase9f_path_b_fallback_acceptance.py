"""Validate and freeze Phase 9F.2B.6 Path B -> Path A fallback acceptance."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from document_engine.evaluation.phase9f import Phase9FDocumentObservation
from document_engine.evaluation.phase9f_fallback_acceptance import (
    Phase9FPathBFallbackAcceptanceFreeze,
    assess_phase9f_path_b_fallback_acceptance,
)
from document_engine.evaluation.phase9f_fallback_verification import (
    Phase9FPathBFallbackVerification,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Validate the privacy-safe Phase 9F.2B.5 fallback artifact against the "
            "tracked Phase 9F.2B.6 acceptance freeze."
        )
    )
    parser.add_argument(
        "--verification",
        default="workspace/phase9f/path_b_fallback_verification.json",
    )
    parser.add_argument(
        "--freeze",
        default="configs/evaluation/phase9f_path_b_fallback_acceptance.yaml",
    )
    parser.add_argument(
        "--output",
        default="workspace/phase9f/path_b_fallback_acceptance.json",
    )
    return parser


def _resolve_file(root: Path, relative_path: str, label: str) -> Path:
    resolved = (root / relative_path).resolve()
    if resolved != root and root not in resolved.parents:
        raise ValueError(f"{label} escaped repository root.")
    if not resolved.is_file():
        raise FileNotFoundError(f"{label} is not available.")
    return resolved


def main() -> int:
    args = _parser().parse_args()
    root = Path.cwd().resolve()

    try:
        verification_path = _resolve_file(root, args.verification, "Fallback verification")
        freeze_path = _resolve_file(root, args.freeze, "Fallback acceptance freeze")

        payload = json.loads(verification_path.read_text(encoding="utf-8"))
        if payload.get("phase") != "9F.2B.5":
            raise ValueError("PHASE_9F2B6_SOURCE_PHASE_MISMATCH")
        if payload.get("private_values_persisted") is not False:
            raise ValueError("PHASE_9F2B6_PRIVACY_CONTRACT_FAILED")

        verification = Phase9FPathBFallbackVerification.model_validate(payload["verification"])
        observation = Phase9FDocumentObservation.model_validate(payload["path_a_observation"])
        metadata = payload["path_a_metadata"]

        acceptance = assess_phase9f_path_b_fallback_acceptance(
            verification=verification,
            observation=observation,
            path_a_metadata=metadata,
        )
        freeze = Phase9FPathBFallbackAcceptanceFreeze.load_yaml(freeze_path)
        freeze.validate_acceptance(acceptance)
    except Exception as exc:
        print(f"PHASE_9F2B6_FALLBACK_ACCEPTANCE_FAILED:{type(exc).__name__}")
        print(f"reason={str(exc)}")
        print("holdout_authorized=false")
        print("private_values_persisted=false")
        return 2

    output_path = (root / args.output).resolve()
    if output_path != root and root not in output_path.parents:
        print("PHASE_9F2B6_FALLBACK_ACCEPTANCE_FAILED:ValueError")
        print("reason=Output path escaped repository root.")
        print("holdout_authorized=false")
        print("private_values_persisted=false")
        return 2

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(
            {
                "phase": "9F.2B.6",
                "acceptance": acceptance.model_dump(mode="json"),
                "freeze_validated": True,
                "private_values_persisted": False,
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    print("PHASE_9F2B6_FALLBACK_ACCEPTANCE")
    print(f"routing_accepted={str(acceptance.routing_accepted).lower()}")
    print(f"fallback_execution_accepted={str(acceptance.fallback_execution_accepted).lower()}")
    print(f"fallback_quality_disposition={acceptance.fallback_quality_disposition.value}")
    print(f"fallback_quality_accepted={str(acceptance.fallback_quality_accepted).lower()}")
    print(f"normalized_match_rate={acceptance.normalized_match_rate}")
    print(f"semantic_path_b_quality_evaluable={str(acceptance.semantic_path_b_quality_evaluable).lower()}")
    print(f"semantic_path_b_quality_accepted={str(acceptance.semantic_path_b_quality_accepted).lower()}")
    print(f"holdout_authorized={str(acceptance.holdout_authorized).lower()}")
    print(f"generalization_claim_authorized={str(acceptance.generalization_claim_authorized).lower()}")
    print("freeze_validated=true")
    print(f"output={args.output}")
    print("private_values_persisted=false")
    return 0


if __name__ == "__main__":
    sys.exit(main())
