"""Prepare and validate the Phase 9F A/B/C evaluation plan without heavy inference."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from document_engine.evaluation.phase9_contract import (
    Phase9EvaluationContract,
    Phase9Manifest,
)
from document_engine.evaluation.phase9f import (
    Phase9FRunContract,
    build_phase9f_plan,
    validate_private_manifest_files,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate Phase 9F contracts and write a privacy-safe A/B/C execution plan."
    )
    parser.add_argument(
        "--contract",
        default="configs/evaluation/phase9_schema.yaml",
        help="Tracked Phase 9 evaluation contract YAML.",
    )
    parser.add_argument(
        "--run-contract",
        default="configs/evaluation/phase9f_run.yaml",
        help="Tracked Phase 9F frozen-path contract YAML.",
    )
    parser.add_argument(
        "--manifest",
        default="workspace/private/phase9/phase9_manifest.yaml",
        help="Private Phase 9 manifest YAML outside git.",
    )
    parser.add_argument(
        "--output",
        default="workspace/phase9f/phase9f_execution_plan.json",
        help="Privacy-safe plan output path.",
    )
    parser.add_argument(
        "--check-private-files",
        action="store_true",
        help="Verify referenced private source/audit files exist without reading their contents.",
    )
    return parser


def main() -> int:
    args = _parser().parse_args()
    repo_root = Path.cwd().resolve()

    contract_path = Path(args.contract)
    run_contract_path = Path(args.run_contract)
    manifest_path = Path(args.manifest)

    for label, path in (
        ("PHASE9_CONTRACT", contract_path),
        ("PHASE9F_RUN_CONTRACT", run_contract_path),
        ("PHASE9_PRIVATE_MANIFEST", manifest_path),
    ):
        if not path.is_file():
            print(f"{label}_MISSING")
            return 2

    try:
        contract = Phase9EvaluationContract.load_yaml(contract_path)
        run_contract = Phase9FRunContract.load_yaml(run_contract_path)
        manifest = Phase9Manifest.load_yaml(manifest_path)
        plan = build_phase9f_plan(contract, manifest, run_contract)

        missing_private_refs = []
        if args.check_private_files:
            missing_private_refs = validate_private_manifest_files(repo_root, manifest)
            if missing_private_refs:
                print("PHASE9_PRIVATE_REFS_MISSING")
                for item in missing_private_refs:
                    print(item)
                return 3
    except Exception as exc:
        print(f"PHASE9F_PLAN_INVALID:{type(exc).__name__}")
        return 4

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(plan.model_dump(mode="json"), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    print("PHASE9F_PLAN_READY")
    print(f"fingerprint={plan.fingerprint}")
    print(f"documents={plan.document_count}")
    print(f"layout_groups={plan.layout_group_count}")
    print(f"planned_path_runs={len(plan.items)}")
    print(f"output={output_path.as_posix()}")
    print("model_loaded=false")
    print("inference_executed=false")
    print("private_values_persisted=false")
    print()
    print("MANUAL_TERMINAL_TASK_REQUIRED")
    print("Next task: Phase 9F.2 per-path execution adapter and one-document dry run.")
    print("Do not run batch A/B/C inference yet.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
