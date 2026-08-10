"""CLI tool to build the private Phase 9 manifest if and only if corpus is eligible."""

import argparse
import sys
from pathlib import Path

import yaml

from document_engine.evaluation.phase9_contract import Phase9Manifest
from document_engine.evaluation.phase9_corpus import (
    Phase9CorpusRegistry,
    evaluate_corpus_readiness,
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
    min_docs = 12
    min_layouts = 4
    frozen_revision = "2eb4b3f7695ef6693369d732a8520fe243269d7a"

    if contract_path.exists():
        contract_data = yaml.safe_load(contract_path.read_text(encoding="utf-8")) or {}
        min_docs = contract_data.get("minimum_documents", 12)
        min_layouts = contract_data.get("minimum_layout_groups", 4)
        frozen_revision = contract_data.get("frozen_baseline_revision", frozen_revision)

    registry_path = Path(args.registry)
    if not registry_path.exists():
        print(f"ERROR: Registry file {args.registry} does not exist.")
        print("PHASE_9F_CORPUS_PREPARATION_REQUIRED")
        return 1

    registry = Phase9CorpusRegistry.load_yaml(registry_path)
    report = evaluate_corpus_readiness(
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
        print(f"missing_audit_count: {report.missing_audit_count}")
        print(f"missing_family_count: {report.missing_family_count}")
        print(f"missing_layout_group_count: {report.missing_layout_group_count}")
        return 1

    # Filter eligible candidates for manifest
    documents_list = []
    for cand in registry.candidates:
        source_path = Path(cand.source_ref)
        audit_path = Path(cand.audit_ref) if cand.audit_ref else None

        # Holdout check
        if cand.cohort == "holdout_same_family" and cand.used_for_prior_tuning:
            continue

        if (
            source_path.exists()
            and audit_path
            and audit_path.exists()
            and cand.family
            and cand.family != "FAMILY_METADATA_MISSING"
            and cand.layout_group
            and cand.layout_group != "LAYOUT_GROUP_METADATA_MISSING"
        ):
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

    # Validate output manifest using Phase9Manifest schema
    try:
        Phase9Manifest.load_yaml(output_path)
    except Exception as e:
        print(f"ERROR: Generated manifest failed validation: {e}")
        if output_path.exists():
            output_path.unlink()
        return 1

    print("PHASE_9F_MANIFEST_CREATED")
    print(f"output_path: {args.output}")
    print(f"document_count: {len(documents_list)}")
    print(f"distinct_layout_groups: {report.distinct_layout_groups}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
