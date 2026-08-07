"""Script to run Private Real-Document Pilot according to pilot_manifest.yaml."""

import argparse
from pathlib import Path
import sys
import yaml

from document_engine.orchestration.pipeline import DocumentPipeline


def main():
    parser = argparse.ArgumentParser(description="Run Private Real-Document Pilot")
    parser.add_argument(
        "--manifest",
        type=str,
        default="workspace/pilot/pilot_manifest.yaml",
        help="Path to private pilot manifest YAML file",
    )
    args = parser.parse_args()

    manifest_path = Path(args.manifest)
    if not manifest_path.exists():
        print(f"Pilot manifest file not found: {manifest_path}")
        print("To run private pilot, copy 'configs/pilot_manifest.example.yaml' to 'workspace/pilot/pilot_manifest.yaml' and set local PDF paths.")
        sys.exit(0)

    with open(manifest_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    documents = data.get("documents", [])
    if not documents:
        print("No document entries found in manifest.")
        sys.exit(0)

    print(f"=== Starting Private Real-Document Pilot ({len(documents)} documents) ===")
    pipeline = DocumentPipeline()

    reports = []
    for entry in documents:
        doc_id = entry.get("id")
        pdf_path = Path(entry.get("path"))
        expected_family = entry.get("expected_family")
        manual_audit = entry.get("manual_audit_status", "NOT_AUDITED")

        if not pdf_path.exists():
            print(f"[{doc_id}] SKIPPED - File not found: {pdf_path}")
            reports.append(
                {
                    "id": doc_id,
                    "status": "SKIPPED_MISSING_FILE",
                    "path": str(pdf_path),
                    "system_validation_status": "skipped",
                    "manual_audit_status": manual_audit,
                }
            )
            continue

        try:
            res = pipeline.process_file(pdf_path)

            extracted_fields = list(res.envelope.field_candidates.keys()) if res.envelope else []
            evidence_count = sum(
                len(c.evidence_references)
                for c in (res.envelope.field_candidates.values() if res.envelope else [])
            )

            report = {
                "id": doc_id,
                "profile": res.pdf_profile,
                "route_parser": res.selected_parser,
                "family": res.document_family,
                "expected_family": expected_family,
                "extracted_fields": extracted_fields,
                "evidence_count": evidence_count,
                "system_validation_status": res.validation_status,
                "completeness_score": res.completeness.completeness_score if res.completeness else 0.0,
                "manual_audit_status": manual_audit,
            }
            reports.append(report)
            print(f"[{doc_id}] {res.pdf_profile} | Parser: {res.selected_parser} | Family: {res.document_family} | Score: {report['completeness_score']:.2f} | Validation: {res.validation_status} | Audit: {manual_audit}")

        except Exception as err:
            print(f"[{doc_id}] ERROR - {err}")
            reports.append({"id": doc_id, "status": "ERROR", "error": str(err), "system_validation_status": "error", "manual_audit_status": manual_audit})

    print("\n=== Pilot Report Summary ===")
    print(yaml.dump({"pilot_results": reports}, sort_keys=False))


if __name__ == "__main__":
    main()
