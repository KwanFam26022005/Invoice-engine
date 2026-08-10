"""Unit tests for Phase 9 corpus models and readiness evaluation logic."""

import json
from pathlib import Path
import pytest

from document_engine.evaluation.phase9_corpus import (
    Phase9CorpusCandidate,
    Phase9CorpusReadinessReport,
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


def test_candidate_path_validation_rejects_absolute_and_traversal() -> None:
    with pytest.raises(ValueError, match="workspace-relative"):
        Phase9CorpusCandidate(
            alias="doc1",
            source_ref="C:/workspace/doc1.pdf",
            family="sales_invoice",
            cohort="current_pilot",
            layout_group="sales_a",
            sha256="dummy",
        )

    with pytest.raises(ValueError, match="parent directory traversal"):
        Phase9CorpusCandidate(
            alias="doc1",
            source_ref="workspace/../secret/doc1.pdf",
            family="sales_invoice",
            cohort="current_pilot",
            layout_group="sales_a",
            sha256="dummy",
        )


def test_candidate_invalid_cohort() -> None:
    with pytest.raises(ValueError, match="Invalid cohort"):
        Phase9CorpusCandidate(
            alias="doc1",
            source_ref="workspace/doc1.pdf",
            family="sales_invoice",
            cohort="invalid_cohort",
            layout_group="sales_a",
            sha256="dummy",
        )


def test_registry_find_and_update(tmp_path: Path) -> None:
    registry = Phase9CorpusRegistry()
    cand1 = Phase9CorpusCandidate(
        alias="alias_1",
        source_ref="workspace/doc1.pdf",
        family="sales_invoice",
        cohort="current_pilot",
        layout_group="layout_a",
        sha256="hash1111",
    )
    registry.add_or_update_candidate(cand1)
    assert registry.find_by_alias("alias_1") == cand1
    assert registry.find_by_sha256("hash1111") == cand1

    # Update candidate
    cand1_updated = cand1.model_copy(update={"family": "utility_consumption_invoice"})
    registry.add_or_update_candidate(cand1_updated)
    assert len(registry.candidates) == 1
    assert registry.find_by_alias("alias_1").family == "utility_consumption_invoice"

    # Save and load
    reg_file = tmp_path / "registry.yaml"
    registry.save_yaml(reg_file)
    loaded = Phase9CorpusRegistry.load_yaml(reg_file)
    assert len(loaded.candidates) == 1
    assert loaded.candidates[0].alias == "alias_1"


def test_count_audit_confirmed_fields(tmp_path: Path) -> None:
    audit_path = tmp_path / "test.audit.json"
    audit_data = {
        "document_id": "test_alias",
        "family": "sales_invoice",
        "fields": {
            "f1": {"status": "CONFIRMED", "expected": "VAL1"},
            "f2": {"status": "audited", "expected": "VAL2"},
            "f3": {"status": "NOT_AUDITED", "expected": None},
            "f4": {"status": "UNCONFIRMED", "expected": None},
        },
    }
    audit_path.write_text(json.dumps(audit_data), encoding="utf-8")

    exists, confirmed_count = count_audit_confirmed_fields(audit_path)
    assert exists is True
    assert confirmed_count == 2


def test_evaluate_corpus_readiness_insufficient(tmp_path: Path) -> None:
    registry = Phase9CorpusRegistry()
    cand = Phase9CorpusCandidate(
        alias="doc1",
        source_ref="workspace/doc1.pdf",
        audit_ref="workspace/doc1.audit.json",
        family="sales_invoice",
        cohort="current_pilot",
        layout_group="layout_a",
        sha256="hash1",
    )
    registry.add_or_update_candidate(cand)

    report = evaluate_corpus_readiness(registry, base_dir=tmp_path, minimum_documents=12, minimum_layout_groups=4)
    assert isinstance(report, Phase9CorpusReadinessReport)
    assert report.registered_documents == 1
    assert report.eligible_documents == 0  # source/audit files don't exist on disk
    assert report.is_ready is False
    assert report.remaining_document_deficit == 12


def test_evaluate_corpus_readiness_holdout_prior_tuning_rejection(tmp_path: Path) -> None:
    ws = tmp_path / "workspace"
    ws.mkdir(parents=True)
    pdf_file = ws / "doc1.pdf"
    pdf_file.write_bytes(b"%PDF-1.4 test")
    audit_file = ws / "doc1.audit.json"
    audit_file.write_text(json.dumps({"fields": {"f1": {"status": "CONFIRMED"}}}), encoding="utf-8")

    registry = Phase9CorpusRegistry()
    cand = Phase9CorpusCandidate(
        alias="holdout_doc",
        source_ref="workspace/doc1.pdf",
        audit_ref="workspace/doc1.audit.json",
        family="sales_invoice",
        cohort="holdout_same_family",
        layout_group="layout_a",
        sha256="hash1",
        used_for_prior_tuning=True,  # Disqualifies from holdout
    )
    registry.add_or_update_candidate(cand)

    report = evaluate_corpus_readiness(registry, base_dir=tmp_path, minimum_documents=12, minimum_layout_groups=4)
    assert report.prior_tuning_holdout_rejections == 1
    assert report.eligible_documents == 0


def test_privacy_report_contains_no_pii_or_paths() -> None:
    report = Phase9CorpusReadinessReport(
        registered_documents=5,
        eligible_documents=3,
        current_pilot_count=3,
        holdout_same_family_count=0,
        unknown_family_count=0,
        distinct_layout_groups=2,
        documents_with_audit=3,
        documents_with_confirmed_audit=3,
        missing_audit_count=2,
        missing_family_count=0,
        missing_layout_group_count=0,
        prior_tuning_holdout_rejections=1,
        duplicate_count=0,
        minimum_documents=12,
        minimum_layout_groups=4,
    )
    rep_str = str(report.model_dump())
    assert "C:" not in rep_str
    assert "D:" not in rep_str
    assert ".pdf" not in rep_str
    assert "expected" not in rep_str
