"""Unit tests for Phase 9 corpus models, readiness evaluation, and strict contracts."""

import json
from pathlib import Path
import pytest

from document_engine.evaluation.audit_models import FieldAuditStatus
from document_engine.evaluation.phase9_corpus import (
    Phase9CorpusCandidate,
    Phase9CorpusRegistry,
    count_audit_confirmed_fields,
    evaluate_corpus_readiness,
)


def test_candidate_valid_creation() -> None:
    cand = Phase9CorpusCandidate(
        alias="test_doc_001",
        source_ref="workspace/private/phase9/documents/doc1.pdf",
        audit_ref="workspace/private/phase9/audit/doc1.audit.json",
        family="sales_invoice",
        cohort="current_pilot",
        layout_group="sales_a",
        sha256="a1b2c3d4e5f67890a1b2c3d4e5f67890a1b2c3d4e5f67890a1b2c3d4e5f67890",
    )
    assert cand.alias == "test_doc_001"
    assert cand.source_ref == "workspace/private/phase9/documents/doc1.pdf"
    assert cand.cohort == "current_pilot"


def test_candidate_path_validation_rejects_non_workspace_relative() -> None:
    # A. Rejects non-workspace relative source (e.g. private/doc.pdf without workspace/ prefix)
    with pytest.raises(ValueError, match="workspace-relative"):
        Phase9CorpusCandidate(
            alias="doc1",
            source_ref="private/doc.pdf",
            family="sales_invoice",
            cohort="current_pilot",
            layout_group="sales_a",
            sha256="dummy",
        )

    # B. Rejects Windows absolute paths
    with pytest.raises(ValueError, match="workspace-relative"):
        Phase9CorpusCandidate(
            alias="doc1",
            source_ref="C:\\private\\doc.pdf",
            family="sales_invoice",
            cohort="current_pilot",
            layout_group="sales_a",
            sha256="dummy",
        )

    with pytest.raises(ValueError, match="workspace-relative"):
        Phase9CorpusCandidate(
            alias="doc1",
            source_ref="D:/private/doc.pdf",
            family="sales_invoice",
            cohort="current_pilot",
            layout_group="sales_a",
            sha256="dummy",
        )

    with pytest.raises(ValueError, match="workspace-relative"):
        Phase9CorpusCandidate(
            alias="doc1",
            source_ref="workspace/../secret/doc1.pdf",
            family="sales_invoice",
            cohort="current_pilot",
            layout_group="sales_a",
            sha256="dummy",
        )


def test_candidate_enum_validation() -> None:
    # F. Invalid DocumentFamilyType rejected
    with pytest.raises(ValueError, match="Invalid DocumentFamilyType"):
        Phase9CorpusCandidate(
            alias="doc1",
            source_ref="workspace/doc1.pdf",
            family="random_invoice_xyz",
            cohort="current_pilot",
            layout_group="sales_a",
            sha256="dummy",
        )

    # G. Invalid PDFProfileType rejected
    with pytest.raises(ValueError, match="Invalid PDFProfileType"):
        Phase9CorpusCandidate(
            alias="doc1",
            source_ref="workspace/doc1.pdf",
            family="sales_invoice",
            cohort="current_pilot",
            expected_profile="invalid_profile_abc",
            layout_group="sales_a",
            sha256="dummy",
        )


def test_strict_audit_status_counting(tmp_path: Path) -> None:
    # C. Only CONFIRMED status counts
    audit_path = tmp_path / "test.audit.json"
    audit_data = {
        "document_id": "test_alias",
        "family": "sales_invoice",
        "fields": {
            "f1": {"status": "CONFIRMED", "expected": "VAL1"},
            "f2": {"status": "NOT_AUDITED", "expected": "VAL2"},
            "f3": {"status": "AMBIGUOUS_SOURCE", "expected": "VAL3"},
            "f4": {"status": "NOT_PRESENT_IN_SOURCE", "expected": "VAL4"},
            "f5": {"status": "ARBITRARY_STATUS", "expected": "VAL5"},
            "f6": "RAW_SCALAR_VAL",
        },
    }
    audit_path.write_text(json.dumps(audit_data), encoding="utf-8")

    exists, confirmed_count = count_audit_confirmed_fields(audit_path)
    assert exists is True
    assert confirmed_count == 1  # Only f1 (status=CONFIRMED) counts!


def test_evaluate_corpus_readiness_duplicate_and_layout_filtering(tmp_path: Path) -> None:
    ws = tmp_path / "workspace"
    ws.mkdir(parents=True)

    # Create source PDFs & audit JSON files
    pdf1 = ws / "doc1.pdf"
    pdf1.write_bytes(b"%PDF-1.4 test 1")
    audit1 = ws / "doc1.audit.json"
    audit1.write_text(json.dumps({"fields": {"f1": {"status": FieldAuditStatus.CONFIRMED.value}}}), encoding="utf-8")

    pdf2 = ws / "doc2.pdf"
    pdf2.write_bytes(b"%PDF-1.4 test 2")
    audit2 = ws / "doc2.audit.json"
    audit2.write_text(json.dumps({"fields": {"f1": {"status": FieldAuditStatus.CONFIRMED.value}}}), encoding="utf-8")

    registry = Phase9CorpusRegistry()

    # Candidate 1 (valid, layout_a)
    c1 = Phase9CorpusCandidate(
        alias="doc1",
        source_ref="workspace/doc1.pdf",
        audit_ref="workspace/doc1.audit.json",
        family="sales_invoice",
        cohort="current_pilot",
        layout_group="layout_a",
        sha256="same_hash_1234",
    )
    registry.add_or_update_candidate(c1)

    # Candidate 2 (duplicate SHA manually inserted, layout_b)
    # H & I: Duplicate SHA is detected and does NOT inflate eligible_documents or distinct_layout_groups
    c2 = Phase9CorpusCandidate(
        alias="doc2",
        source_ref="workspace/doc2.pdf",
        audit_ref="workspace/doc2.audit.json",
        family="sales_invoice",
        cohort="holdout_same_family",
        layout_group="layout_b",
        sha256="same_hash_1234",  # Duplicate hash
    )
    registry.add_or_update_candidate(c2)

    # Candidate 3 (ineligible due to prior tuning, layout_c)
    # J & K: Ineligible prior-tuning layout group does NOT count toward layout_groups
    c3 = Phase9CorpusCandidate(
        alias="doc3",
        source_ref="workspace/doc1.pdf",
        audit_ref="workspace/doc1.audit.json",
        family="sales_invoice",
        cohort="holdout_same_family",
        layout_group="layout_c",
        sha256="hash_3333",
        used_for_prior_tuning=True,
    )
    registry.add_or_update_candidate(c3)

    report = evaluate_corpus_readiness(registry, base_dir=tmp_path, minimum_documents=12, minimum_layout_groups=4)
    assert report.registered_documents == 3
    assert report.duplicate_count == 1
    assert report.prior_tuning_holdout_rejections == 1
    assert report.eligible_documents == 1  # Only c1 is eligible!
    assert report.distinct_layout_groups == 1  # Only layout_a from c1 counts!


def test_unrelated_incomplete_candidate_does_not_block_valid_selected_corpus(tmp_path: Path) -> None:
    # L. An unrelated incomplete intake candidate does not prevent a valid 12-document selected corpus from being ready
    ws = tmp_path / "workspace"
    ws.mkdir(parents=True)

    registry = Phase9CorpusRegistry()
    cohorts = ["current_pilot", "holdout_same_family", "unknown_family"]
    layouts = ["layout_a", "layout_b", "layout_c", "layout_d"]

    for i in range(12):
        alias = f"eligible_doc_{i+1:03d}"
        pdf_path = ws / f"{alias}.pdf"
        pdf_path.write_bytes(f"%PDF-1.4 content {i}".encode())
        audit_path = ws / f"{alias}.audit.json"
        audit_path.write_text(
            json.dumps({"fields": {"common.doc_num": {"status": "CONFIRMED", "expected": f"VAL{i}"}}}),
            encoding="utf-8",
        )
        registry.add_or_update_candidate(
            Phase9CorpusCandidate(
                alias=alias,
                source_ref=f"workspace/{alias}.pdf",
                audit_ref=f"workspace/{alias}.audit.json",
                family="sales_invoice" if i % 2 == 0 else "receipt",
                cohort=cohorts[i % len(cohorts)],
                layout_group=layouts[i % len(layouts)],
                sha256=f"hash_unique_{i:04d}",
            )
        )

    # Add an 13th incomplete candidate missing audit file & source file
    registry.add_or_update_candidate(
        Phase9CorpusCandidate(
            alias="incomplete_doc_013",
            source_ref="workspace/missing.pdf",
            audit_ref="workspace/missing.audit.json",
            family="sales_invoice",
            cohort="current_pilot",
            layout_group="layout_incomplete",
            sha256="hash_incomplete_9999",
        )
    )

    report = evaluate_corpus_readiness(registry, base_dir=tmp_path, minimum_documents=12, minimum_layout_groups=4)
    assert report.registered_documents == 13
    assert report.eligible_documents == 12
    assert report.distinct_layout_groups == 4
    assert report.missing_audit_count == 1
    assert report.is_ready is True  # Ready despite the 13th incomplete candidate!
