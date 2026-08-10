"""CLI tool to create a private audit JSON skeleton with NOT_AUDITED status derived from schema_registry.py."""

import argparse
import json
import sys
from pathlib import Path
from typing import Any, List

from document_engine.core.models import DocumentFamilyType
from document_engine.semantic.schema_registry import get_semantic_schema, supports_semantic_schema


def flatten_template(data: Any, prefix: str = "") -> List[str]:
    """Recursively extract scalar field paths from a semantic schema template.

    List fields (e.g. line_items, meter_readings, pricing_tiers) are skipped
    to prevent fabricating arbitrary row indices in ground-truth skeletons.
    """
    paths: List[str] = []
    if isinstance(data, dict):
        for k, v in data.items():
            new_prefix = f"{prefix}.{k}" if prefix else k
            if isinstance(v, dict):
                paths.extend(flatten_template(v, new_prefix))
            elif isinstance(v, list):
                # Scalar skeleton strategy: omit list row index fabrication
                pass
            else:
                paths.append(new_prefix)
    return paths


def derive_canonical_field_paths(family: str) -> List[str]:
    """Derive canonical scalar field paths from schema_registry.py."""
    try:
        family_enum = DocumentFamilyType(family)
    except ValueError:
        return []

    if not supports_semantic_schema(family_enum):
        return []

    spec = get_semantic_schema(family_enum)
    return flatten_template(spec.template)


def main() -> int:
    parser = argparse.ArgumentParser(description="Create a Phase 9 audit JSON skeleton for a document.")
    parser.add_argument("--alias", "--document-id", dest="alias", required=True, help="Opaque document alias / ID")
    parser.add_argument("--family", required=True, help="Document family")
    parser.add_argument("--output", required=True, help="Output path for audit JSON file")

    args = parser.parse_args()

    # Validate DocumentFamilyType
    try:
        DocumentFamilyType(args.family)
    except ValueError:
        print("ERROR: INVALID_FAMILY_TYPE")
        return 1

    field_paths = derive_canonical_field_paths(args.family)
    fields_dict = {}

    for field_path in field_paths:
        fields_dict[field_path] = {
            "expected": None,
            "status": "NOT_AUDITED",
            "notes": None,
        }

    audit_data = {
        "document_id": args.alias,
        "family": args.family,
        "fields": fields_dict,
    }

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(audit_data, indent=2), encoding="utf-8")

    print(f"AUDIT_SKELETON_CREATED: alias={args.alias}, field_count={len(fields_dict)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
