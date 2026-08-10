"""Manual-terminal runner for one Phase 9F.2B Docling semantic dry run."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from document_engine.evaluation.phase9f_path_b import (
    execute_phase9f_path_b_observation,
    probe_phase9f_path_b_alias,
)


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
        "--execute",
        action="store_true",
        help="Explicitly permit the real local Docling/NuExtract model call.",
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


def main() -> int:
    args = _parser().parse_args()
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
        print("model_loaded=false")
        print("inference_executed=false")
        print("private_values_persisted=false")
        print("MANUAL_TERMINAL_TASK_REQUIRED")
        print(
            "Run again from the dedicated local semantic environment with --execute "
            "after confirming offline model artifacts are ready."
        )
        return 0

    try:
        observation, metadata = execute_phase9f_path_b_observation(
            alias=args.alias,
            repo_root=repo_root,
            manifest_path=args.manifest,
            allow_heavy_execution=True,
        )
    except Exception as exc:
        print(f"PHASE_9F2B_DRY_RUN_FAILED:{type(exc).__name__}")
        return 4

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
    print(f"predicted_family={metadata['predicted_family']}")
    print(f"candidate_count={metadata['candidate_count']}")
    print(f"grounded_count={metadata['grounded_count']}")
    print(f"unsupported_count={metadata['unsupported_count']}")
    print(f"abstained_count={metadata['abstained_count']}")
    print(f"output={output_path.as_posix()}")
    print("private_values_persisted=false")
    return 0 if metadata["semantic_success"] else 5


if __name__ == "__main__":
    sys.exit(main())
