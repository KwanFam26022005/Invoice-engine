"""Unit tests for Phase 9 corpus models, ground-truth completeness, and cohort semantics."""

import hashlib
import json
from pathlib import Path
import pytest

from document_engine.evaluation.audit_models import FieldAuditStatus
from document_engine.evaluation.phase9_corpus import (
    Phase9CorpusCandidate,
    Phase9CorpusRegistry,
    compute_file_sha256,
    evaluate_corpus_readiness,
    is_cohort_family_compatible,
    select_evaluation_ready_candidates,
)


def test_candidate_valid_creation() -> None:
    cand = Phase9CorpusCandidate(
        alias="test_doc_001",
        source_ref="workspace/private/phase9/documents/doc1.pdf",
        audit_ref="workspace/private/phase9/audit/doc1.audit.json",
        family="sales_invoice",
        cohort="current_pilot",
        layout_group="sales_a",
        sha256="a" * 64,
    )
    assert cand.alias == "test_doc_001"
    assert cand.source_ref == "workspace/private/phase9/documents/doc1.pdf"
    assert cand.cohort == "current_pilot"


def test_sha256_validation() -> None:
    # J. Invalid SHA rejected
    with pytest.raises(ValueError, match="64 hexadecimal characters"):
        Phase9CorpusCandidate(
            alias="doc1",
            source_ref="workspace/doc1.pdf",
            family="sales_invoice",
            cohort="current_pilot",
            layout_group="sales_a",
            sha256="hash1",
        )

    # K. Valid 64-hex SHA accepted
    cand = Phase9CorpusCandidate(
        alias="doc1",
        source_ref="workspace/doc1.pdf",
        family="sales_invoice",
        cohort="current_pilot",
        layout_group="sales_a",
        sha256="b" * 64,
    )
    assert cand.sha256 == "b" * 64


def test_registry_unique_aliases_validation() -> None:
    # I. Duplicate aliases in manually constructed registry YAML fails validation
    registry = Phase9CorpusRegistry()
    cand1 = Phase9CorpusCandidate(
        alias="duplicate_alias",
        source_ref="workspace/doc1.pdf",
        family="sales_invoice",
        cohort="current_pilot",
        layout_group="layout_a",
        sha256="1" * 64,
    )
    cand2 = Phase9CorpusCandidate(
        alias="duplicate_alias",
        source_ref="workspace/doc2.pdf",
        family="sales_invoice",
        cohort="current_pilot",
        layout_group="layout_b",
        sha256="2" * 64,
    )
    registry.candidates = [cand1, cand2]

    with pytest.raises(ValueError, match="aliases must be unique"):
        registry.validate_unique_aliases()


def test_cohort_family_semantic_compatibility() -> None:
    # E. sales_invoice + unknown_family -> rejected
    assert is_cohort_family_compatible("unknown_family", "sales_invoice") is False

    # F. receipt + holdout_same_family -> rejected
    assert is_cohort_family_compatible("holdout_same_family", "receipt") is False

    # G. receipt + unknown_family -> eligible
    assert is_cohort_family_compatible("unknown_family", "receipt") is True

    # H. sales_invoice + holdout_same_family -> eligible
    assert is_cohort_family_compatible("holdout_same_family", "sales_invoice") is True

    # current_pilot -> eligible for any valid family
    assert is_cohort_family_compatible("current_pilot", "sales_invoice") is True
    assert is_cohort_family_compatible("current_pilot", "receipt") is True


def test_ground_truth_completeness_rules(tmp_path: Path) -> None:
    ws = tmp_path / "workspace"
    ws.mkdir(parents=True)
    pdf = ws / "doc1.pdf"
    pdf.write_bytes(b"%PDF-1.4 test")

    # A. audit exists, all fields NOT_AUDITED -> eligible_documents == 0, documents_without_confirmed_fields == 1
    audit_not_audited = ws / "doc1_not_audited.audit.json"
    audit_not_audited.write_text(
        json.dumps({"fields": {"f1": {"status": "NOT_AUDITED", "expected": None}}}),
        encoding="utf-8",
    )

    reg1 = Phase9CorpusRegistry()
    cand1 = Phase9CorpusCandidate(
        alias="doc1",
        source_ref="workspace/doc1.pdf",
        audit_ref="workspace/doc1_not_audited.audit.json",
        family="sales_invoice",
        cohort="current_pilot",
        layout_group="layout_a",
        sha256="a" * 64,
    )
    reg1.add_or_update_candidate(cand1)
    eligible1, report1 = select_evaluation_ready_candidates(reg1, base_dir=tmp_path)
    assert len(eligible1) == 0
    assert report1.eligible_documents == 0
    assert report1.documents_without_confirmed_fields == 1

    # B. same document with one CONFIRMED field -> may become eligible when other requirements pass
    audit_confirmed = ws / "doc1_confirmed.audit.json"
    audit_confirmed.write_text(
        json.dumps({"fields": {"f1": {"status": FieldAuditStatus.CONFIRMED.value, "expected": "VAL1"}}}),
        encoding="utf-8",
    )

    reg2 = Phase9CorpusRegistry()
    cand2 = Phase9CorpusCandidate(
        alias="doc1",
        source_ref="workspace/doc1.pdf",
        audit_ref="workspace/doc1_confirmed.audit.json",
        family="sales_invoice",
        cohort="current_pilot",
        layout_group="layout_a",
        sha256="a" * 64,
    )
    reg2.add_or_update_candidate(cand2)
    eligible2, report2 = select_evaluation_ready_candidates(reg2, base_dir=tmp_path)
    assert len(eligible2) == 1
    assert report2.eligible_documents == 1
    assert report2.documents_with_confirmed_audit == 1


def test_12_documents_not_audited_readiness_false(tmp_path: Path) -> None:
    # C. 12 source/audit/layout-valid documents but every audit has zero CONFIRMED -> readiness false
    ws = tmp_path / "workspace"
    ws.mkdir(parents=True)

    reg = Phase9CorpusRegistry()
    cohorts = ["current_pilot", "holdout_same_family", "unknown_family"]
    families = ["sales_invoice", "utility_consumption_invoice", "receipt"]
    layouts = ["l1", "l2", "l3", "l4"]

    for i in range(12):
        alias = f"doc_{i+1:03d}"
        pdf = ws / f"{alias}.pdf"
        pdf.write_bytes(f"%PDF-1.4 content {i}".encode())
        audit = ws / f"{alias}.audit.json"
        audit.write_text(json.dumps({"fields": {"f1": {"status": "NOT_AUDITED"}}}), encoding="utf-8")

        cohort = cohorts[i % len(cohorts)]
        family = families[0] if cohort == "holdout_same_family" else (families[2] if cohort == "unknown_family" else families[1])
        sha = hashlib.sha256(f"seed_{i}".encode()).hexdigest()

        reg.add_or_update_candidate(
            Phase9CorpusCandidate(
                alias=alias,
                source_ref=f"workspace/{alias}.pdf",
                audit_ref=f"workspace/{alias}.audit.json",
                family=family,
                cohort=cohort,
                layout_group=layouts[i % len(layouts)],
                sha256=sha,
            )
        )

    report = evaluate_corpus_readiness(reg, base_dir=tmp_path)
    assert report.registered_documents == 12
    assert report.eligible_documents == 0
    assert report.documents_without_confirmed_fields == 12
    assert report.is_ready is False


def test_12_documents_confirmed_gt_readiness_true(tmp_path: Path) -> None:
    # D. 12 valid documents with confirmed GT, correct cohorts, >=4 layouts -> readiness true
    ws = tmp_path / "workspace"
    ws.mkdir(parents=True)

    reg = Phase9CorpusRegistry()
    cohorts = ["current_pilot", "holdout_same_family", "unknown_family"]
    layouts = ["l1", "l2", "l3", "l4"]

    for i in range(12):
        alias = f"doc_{i+1:03d}"
        pdf = ws / f"{alias}.pdf"
        pdf.write_bytes(f"%PDF-1.4 content {i}".encode())
        audit = ws / f"{alias}.audit.json"
        audit.write_text(
            json.dumps({"fields": {"f1": {"status": FieldAuditStatus.CONFIRMED.value, "expected": f"V{i}"}}}),
            encoding="utf-8",
        )

        cohort = cohorts[i % len(cohorts)]
        family = "sales_invoice" if cohort == "holdout_same_family" else ("receipt" if cohort == "unknown_family" else "tax_withholding_certificate")
        sha = hashlib.sha256(f"seed_{i}".encode()).hexdigest()

        reg.add_or_update_candidate(
            Phase9CorpusCandidate(
                alias=alias,
                source_ref=f"workspace/{alias}.pdf",
                audit_ref=f"workspace/{alias}.audit.json",
                family=family,
                cohort=cohort,
                layout_group=layouts[i % len(layouts)],
                sha256=sha,
            )
        )

    report = evaluate_corpus_readiness(reg, base_dir=tmp_path)
    assert report.registered_documents == 12
    assert report.eligible_documents == 12
    assert report.distinct_layout_groups == 4
    assert report.is_ready is True


def test_streaming_sha256_helper(tmp_path: Path) -> None:
    # N. streaming SHA helper returns expected SHA on a synthetic temporary PDF byte fixture
    pdf_file = tmp_path / "test.pdf"
    content = b"%PDF-1.4 synthetic test pdf stream content 12345"
    pdf_file.write_bytes(content)

    expected_sha = hashlib.sha256(content).hexdigest()
    computed_sha = compute_file_sha256(pdf_file, chunk_size=8)
    assert computed_sha == expected_sha
