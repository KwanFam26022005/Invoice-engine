"""CLI tool to create a private audit JSON skeleton with NOT_AUDITED status and null expected values."""

import argparse
import json
import sys
from pathlib import Path

CANONICAL_FAMILY_FIELDS = {
    "sales_invoice": [
        "common.document_number",
        "common.document_date",
        "common.supplier_name",
        "common.supplier_tax_id",
        "common.customer_name",
        "common.customer_tax_id",
        "common.total_amount",
        "common.tax_amount",
        "common.net_amount",
        "common.currency",
    ],
    "utility_consumption_invoice": [
        "common.document_number",
        "common.document_date",
        "common.supplier_name",
        "common.customer_name",
        "common.total_amount",
        "common.tax_amount",
        "utility.meter_number",
        "utility.consumption_kwh",
        "utility.billing_period_start",
        "utility.billing_period_end",
    ],
    "tax_withholding_certificate": [
        "common.document_number",
        "common.document_date",
        "common.supplier_name",
        "common.supplier_tax_id",
        "common.customer_name",
        "common.customer_tax_id",
        "common.total_amount",
        "tax.withheld_amount",
        "tax.income_type",
        "tax.tax_rate",
    ],
}


def main() -> int:
    parser = argparse.ArgumentParser(description="Create a Phase 9 audit JSON skeleton for a document.")
    parser.add_argument("--alias", "--document-id", dest="alias", required=True, help="Opaque document alias / ID")
    parser.add_argument("--family", required=True, help="Document family")
    parser.add_argument("--output", required=True, help="Output path for audit JSON file")

    args = parser.parse_args()

    field_names = CANONICAL_FAMILY_FIELDS.get(args.family, [])
    fields_dict = {}

    for field_name in field_names:
        fields_dict[field_name] = {
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

    print(f"AUDIT_SKELETON_CREATED: alias={args.alias}, family={args.family}, field_count={len(fields_dict)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
