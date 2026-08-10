"""CLI tool to evaluate and print privacy-safe Phase 9 corpus readiness statistics."""

import argparse
import sys
from pathlib import Path

import yaml

from document_engine.evaluation.phase9_corpus import (
    Phase9CorpusRegistry,
    evaluate_corpus_readiness,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate Phase 9 private corpus readiness.")
    parser.add_argument(
        "--registry",
        default="workspace/private/phase9/corpus_registry.yaml",
        help="Path to private corpus registry YAML",
    )
    parser.add_argument(
        "--contract",
        default="configs/evaluation/phase9_schema.yaml",
        help="Path to Phase 9 schema contract YAML",
    )

    args = parser.parse_args()

    min_docs = 12
    min_layouts = 4
    contract_path = Path(args.contract)
    if not contract_path.exists():
        fallback = Path(__file__).resolve().parents[1] / args.contract
        if fallback.exists():
            contract_path = fallback

    if contract_path.exists():
        contract_data = yaml.safe_load(contract_path.read_text(encoding="utf-8")) or {}
        min_docs = contract_data.get("minimum_documents", 12)
        min_layouts = contract_data.get("minimum_layout_groups", 4)

    registry_path = Path(args.registry)
    if not registry_path.exists():
        print("ERROR: REGISTRY_NOT_FOUND")
        print("VERDICT: PHASE_9F_CORPUS_PREPARATION_REQUIRED")
        return 1

    registry = Phase9CorpusRegistry.load_yaml(registry_path)
    report = evaluate_corpus_readiness(
        registry,
        base_dir=Path("."),
        minimum_documents=min_docs,
        minimum_layout_groups=min_layouts,
    )

    print("# PHASE 9 CORPUS READINESS REPORT")
    print(f"registered_documents: {report.registered_documents}")
    print(f"eligible_documents: {report.eligible_documents}")
    print(f"current_pilot_count: {report.current_pilot_count}")
    print(f"holdout_same_family_count: {report.holdout_same_family_count}")
    print(f"unknown_family_count: {report.unknown_family_count}")
    print(f"distinct_layout_groups: {report.distinct_layout_groups}")
    print(f"documents_with_audit: {report.documents_with_audit}")
    print(f"documents_with_confirmed_audit: {report.documents_with_confirmed_audit}")
    print(f"documents_without_confirmed_fields: {report.documents_without_confirmed_fields}")
    print(f"missing_audit_count: {report.missing_audit_count}")
    print(f"missing_family_count: {report.missing_family_count}")
    print(f"missing_layout_group_count: {report.missing_layout_group_count}")
    print(f"prior_tuning_holdout_rejections: {report.prior_tuning_holdout_rejections}")
    print(f"duplicate_count: {report.duplicate_count}")
    print(f"minimum_documents: {report.minimum_documents}")
    print(f"minimum_layout_groups: {report.minimum_layout_groups}")
    print(f"remaining_document_deficit: {report.remaining_document_deficit}")

    if report.is_ready:
        print("VERDICT: PHASE_9F_MANIFEST_LOCKED_PLAN_READY")
        return 0
    else:
        print("VERDICT: PHASE_9F_CORPUS_PREPARATION_REQUIRED")
        return 0


if __name__ == "__main__":
    sys.exit(main())
