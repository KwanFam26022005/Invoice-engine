"""Script to run Private Real-Document Pilot (Phase 8 V2) with audit evaluation and privacy protections."""

import argparse
import json
from pathlib import Path
import sys
import yaml

from document_engine.evaluation import DocumentAuditSpec, Evaluator
from document_engine.ir.models import generate_run_id
from document_engine.orchestration.pipeline import DocumentPipeline


def main():
    parser = argparse.ArgumentParser(description="Run Private Real-Document Pilot V2")
    parser.add_argument(
        "--manifest",
        type=str,
        default="workspace/pilot/pilot_manifest.yaml",
        help="Path to private pilot manifest YAML file",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="workspace/pilot/reports",
        help="Directory to persist machine-readable report JSON",
    )
    args = parser.parse_args()

    manifest_path = Path(args.manifest)
    if not manifest_path.exists():
        print("Pilot manifest file not found.")
        print("To run private pilot, copy 'configs/pilot_manifest.example.yaml' to 'workspace/pilot/pilot_manifest.yaml' and set local PDF paths.")
        sys.exit(0)

    with open(manifest_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    documents = data.get("documents", [])
    if not documents:
        print("No document entries found in manifest.")
        sys.exit(0)

    run_id = generate_run_id()
    print(f"=== Starting Private Real-Document Pilot V2 (Run ID: {run_id}, {len(documents)} documents) ===")

    pipeline = DocumentPipeline()
    evaluator = Evaluator()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    document_summaries = []
    doc_reports = []

    for entry in documents:
        doc_id = entry.get("id", "doc_unknown")
        pdf_path = Path(entry.get("path", ""))
        expected_family = entry.get("expected_family")
        expected_profile = entry.get("expected_profile")
        manual_audit = entry.get("manual_audit_status", "NOT_AUDITED")

        if not pdf_path.exists():
            print(f"[{doc_id}] SKIPPED - File not found")
            doc_reports.append(
                {
                    "document_id": doc_id,
                    "status": "SKIPPED_MISSING_FILE",
                    "manual_audit_status": manual_audit,
                }
            )
            continue

        try:
            res = pipeline.process_file(pdf_path, run_id=run_id)

            # Check if private audit file exists
            audit_path = Path(f"workspace/pilot/audit/{doc_id}.audit.json")
            audit_spec = None
            if audit_path.exists():
                try:
                    with open(audit_path, "r", encoding="utf-8") as f_aud:
                        audit_data = json.load(f_aud)
                        audit_spec = DocumentAuditSpec.model_validate(audit_data)
                except Exception as e_aud:
                    print(f"[{doc_id}] Warning loading audit spec: {type(e_aud).__name__}")

            eval_summary = evaluator.evaluate_document(res, audit_spec)
            document_summaries.append(eval_summary)

            comp_score = res.completeness.completeness_score if res.completeness else 0.0
            field_cand_cnt = len(res.envelope.field_candidates) if res.envelope else 0

            profile_match = (res.pdf_profile == expected_profile) if expected_profile else True
            family_match = (res.document_family == expected_family) if expected_family else True

            attempt_cnt = 1
            if res.routing_decision and res.routing_decision.attempt_number:
                attempt_cnt = res.routing_decision.attempt_number

            doc_rep = {
                "document_id": doc_id,
                "profile": res.pdf_profile,
                "expected_profile": expected_profile,
                "profile_match": profile_match,
                "selected_parser": res.selected_parser,
                "parser_attempt_count": attempt_cnt,
                "family": res.document_family,
                "expected_family": expected_family,
                "family_match": family_match,
                "completeness_score": comp_score,
                "field_candidate_count": field_cand_cnt,
                "evidence_coverage": eval_summary.evidence_coverage,
                "validation_status": res.validation_status,
                "review_required": res.requires_review,
                "manual_audit_status": manual_audit,
                "failure_categories": [cat.value for cat in eval_summary.failure_categories],
            }
            doc_reports.append(doc_rep)

            print(
                f"[{doc_id}] {res.pdf_profile} | Parser: {res.selected_parser} (attempts: {attempt_cnt}) | "
                f"Family: {res.document_family} | Score: {comp_score:.2f} | "
                f"Validation: {res.validation_status} | Failures: {[c.value for c in eval_summary.failure_categories]}"
            )

        except Exception as err:
            err_type = type(err).__name__
            print(f"[{doc_id}] ERROR - {err_type}")
            doc_reports.append(
                {
                    "document_id": doc_id,
                    "status": "ERROR",
                    "error_type": err_type,
                    "safe_error_code": "PIPELINE_PROCESSING_ERROR",
                    "manual_audit_status": manual_audit,
                }
            )

    aggregate_report = evaluator.aggregate_summaries(document_summaries)

    final_report = {
        "run_id": run_id,
        "total_manifest_entries": len(documents),
        "processed_documents": len(document_summaries),
        "aggregate_metrics": aggregate_report.model_dump(),
        "document_reports": doc_reports,
    }

    report_file = output_dir / f"{run_id}.json"
    with open(report_file, "w", encoding="utf-8") as f_out:
        json.dump(final_report, f_out, indent=2, ensure_ascii=False)

    print(f"\n=== Pilot Report Persisted: {report_file.name} ===")
    print(f"Processed: {len(document_summaries)} / {len(documents)}")
    print(f"Total Audited Fields (Confirmed Denominator): {aggregate_report.total_audited_fields}")
    print(f"Exact Match Rate: {aggregate_report.exact_match_rate:.2%}")
    print(f"Normalized Match Rate: {aggregate_report.normalized_match_rate:.2%}")
    print(f"Failure Category Distribution: {aggregate_report.failure_category_counts}")


if __name__ == "__main__":
    main()
