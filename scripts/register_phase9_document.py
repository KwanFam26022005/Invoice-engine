"""CLI tool to register a private PDF into the Phase 9 corpus registry safely."""

import argparse
import hashlib
import sys
from pathlib import Path

from document_engine.evaluation.phase9_corpus import (
    Phase9CorpusCandidate,
    Phase9CorpusRegistry,
    count_audit_confirmed_fields,
)


def parse_bool(val: str) -> bool:
    if isinstance(val, bool):
        return val
    s = str(val).strip().lower()
    if s in {"true", "1", "yes", "y"}:
        return True
    if s in {"false", "0", "no", "n"}:
        return False
    raise ValueError(f"Invalid boolean value '{val}'")


def main() -> int:
    parser = argparse.ArgumentParser(description="Register a private PDF document into Phase 9 corpus registry.")
    parser.add_argument("--source", required=True, help="Workspace-relative path to source PDF")
    parser.add_argument("--alias", required=True, help="Opaque document alias")
    parser.add_argument("--family", required=True, help="Document family")
    parser.add_argument("--cohort", required=True, choices=["current_pilot", "holdout_same_family", "unknown_family"])
    parser.add_argument("--layout-group", required=True, help="Operator-assigned layout group")
    parser.add_argument("--expected-profile", default=None, help="Optional expected profile (e.g. scan_pdf)")
    parser.add_argument("--audit", default=None, help="Optional workspace-relative path to audit JSON")
    parser.add_argument(
        "--used-for-prior-tuning",
        type=parse_bool,
        default=False,
        help="Whether document was used for prior R2/R3 tuning",
    )
    parser.add_argument(
        "--registry",
        default="workspace/private/phase9/corpus_registry.yaml",
        help="Path to private corpus registry YAML",
    )

    args = parser.parse_args()

    source_path = Path(args.source)
    if not source_path.exists() or not source_path.is_file():
        print("ERROR: Source file does not exist.")
        return 1

    if source_path.suffix.lower() != ".pdf":
        print(f"ERROR: Source file must have .pdf extension, got '{source_path.suffix}'")
        return 1

    if args.cohort == "holdout_same_family" and args.used_for_prior_tuning:
        print("ERROR: Document used for prior tuning cannot be registered into holdout_same_family cohort.")
        return 1

    # Calculate SHA256
    pdf_bytes = source_path.read_bytes()
    sha256_hash = hashlib.sha256(pdf_bytes).hexdigest()

    registry_path = Path(args.registry)
    registry = Phase9CorpusRegistry.load_yaml(registry_path)

    # Check duplicates
    existing_sha = registry.find_by_sha256(sha256_hash)
    if existing_sha and existing_sha.alias != args.alias:
        print("ERROR: Exact duplicate document already registered under a different alias.")
        return 1

    confirmed_count = 0
    audit_ref = args.audit
    if audit_ref:
        audit_path = Path(audit_ref)
        if not audit_path.exists():
            print("WARNING: Specified audit reference file does not exist yet.")
        else:
            _, confirmed_count = count_audit_confirmed_fields(audit_path)

    candidate = Phase9CorpusCandidate(
        alias=args.alias,
        source_ref=args.source,
        audit_ref=audit_ref,
        family=args.family,
        cohort=args.cohort,
        expected_profile=args.expected_profile,
        layout_group=args.layout_group,
        sha256=sha256_hash,
        used_for_prior_tuning=args.used_for_prior_tuning,
        audit_confirmed_field_count=confirmed_count,
    )

    registry.add_or_update_candidate(candidate)
    registry.save_yaml(registry_path)

    print(f"REGISTERED_CANDIDATE: alias={candidate.alias}")
    print(f"cohort={candidate.cohort}")
    print(f"family={candidate.family}")
    print(f"layout_group={candidate.layout_group}")
    print(f"total_registered_documents={len(registry.candidates)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
