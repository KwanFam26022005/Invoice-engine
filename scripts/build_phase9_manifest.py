"""CLI tool to build the private Phase 9 manifest if and only if corpus is eligible."""

import argparse
import sys
from pathlib import Path

import yaml

from document_engine.evaluation.phase9_contract import Phase9EvaluationContract, Phase9Manifest
from document_engine.evaluation.phase9_corpus import (
    Phase9CorpusRegistry,
    select_evaluation_ready_candidates,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Build private Phase 9 manifest if corpus passes readiness contract.")
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
    parser.add_argument(
        "--output",
        default="workspace/private/phase9/phase9_manifest.yaml",
        help="Output path for private Phase 9 manifest YAML",
    )

    args = parser.parse_args()

    contract_path = Path(args.contract)
    if not contract_path.exists():
        fallback = Path(__file__).resolve().parents[1] / args.contract
        if fallback.exists():
            contract_path = fallback
        else:
            print("ERROR: CONTRACT_NOT_FOUND")
            print("PHASE_9F_CORPUS_PREPARATION_REQUIRED")
            return 1

    try:
        eval_contract = Phase9EvaluationContract.load_yaml(contract_path)
    except Exception:
        print("ERROR: CONTRACT_LOAD_FAILED")
        print("PHASE_9F_CORPUS_PREPARATION_REQUIRED")
        return 1

    min_docs = eval_contract.minimum_documents
    min_layouts = eval_contract.minimum_layout_groups
    frozen_revision = eval_contract.frozen_baseline_revision

    registry_path = Path(args.registry)
    if not registry_path.exists():
        print("ERROR: REGISTRY_NOT_FOUND")
        print("PHASE_9F_CORPUS_PREPARATION_REQUIRED")
        return 1

    registry = Phase9CorpusRegistry.load_yaml(registry_path)

    # Use shared evaluation-ready candidate selector
    eligible_candidates, report = select_evaluation_ready_candidates(
        registry,
        base_dir=Path("."),
        minimum_documents=min_docs,
        minimum_layout_groups=min_layouts,
    )

    if not report.is_ready:
        print("PHASE_9F_CORPUS_PREPARATION_REQUIRED")
        print(f"eligible_documents: {report.eligible_documents} (minimum required: {min_docs})")
        print(f"current_pilot_count: {report.current_pilot_count}")
        print(f"holdout_same_family_count: {report.holdout_same_family_count}")
        print(f"unknown_family_count: {report.unknown_family_count}")
        print(f"distinct_layout_groups: {report.distinct_layout_groups} (minimum required: {min_layouts})")
        print(f"documents_with_audit: {report.documents_with_audit}")
        print(f"documents_with_confirmed_audit: {report.documents_with_confirmed_audit}")
        print(f"documents_without_confirmed_fields: {report.documents_without_confirmed_fields}")
        print(f"missing_audit_count: {report.missing_audit_count}")
        print(f"missing_family_count: {report.missing_family_count}")
        print(f"missing_layout_group_count: {report.missing_layout_group_count}")
        print(f"cohort_family_mismatch_count: {report.cohort_family_mismatch_count}")
        print(f"duplicate_count: {report.duplicate_count}")
        return 1

    # Format evaluation-ready candidates into manifest document entries
    documents_list = []
    for cand in eligible_candidates:
        doc_entry = {
            "alias": cand.alias,
            "family": cand.family,
            "cohort": cand.cohort,
            "layout_group": cand.layout_group,
            "source_ref": str(cand.source_ref).replace("\\", "/"),
            "audit_ref": str(cand.audit_ref).replace("\\", "/"),
        }
        if cand.expected_profile:
            doc_entry["expected_profile"] = cand.expected_profile
        documents_list.append(doc_entry)

    manifest_data = {
        "manifest_version": "1.0",
        "frozen_baseline_revision": frozen_revision,
        "documents": documents_list,
    }

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(yaml.safe_dump(manifest_data, sort_keys=False), encoding="utf-8")

    # Validate output manifest using Phase9Manifest schema & Phase9EvaluationContract
    try:
        manifest_obj = Phase9Manifest.load_yaml(output_path)
        eval_contract.validate_manifest(manifest_obj)
    except Exception:
        print("ERROR: MANIFEST_VALIDATION_FAILED")
        if output_path.exists():
            output_path.unlink()
        return 1

    print("PHASE_9F_MANIFEST_CREATED")
    print(f"document_count: {len(documents_list)}")
    print(f"distinct_layout_groups: {report.distinct_layout_groups}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
