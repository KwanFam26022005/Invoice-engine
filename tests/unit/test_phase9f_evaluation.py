"""Unit tests for Phase 9F controlled A/B/C planning and safe aggregation."""

from pathlib import Path

import pytest

from document_engine.core.models import DocumentFamilyType, PDFProfileType
from document_engine.evaluation.phase9_contract import (
    EvaluationCohort,
    Phase9DocumentManifestEntry,
    Phase9EvaluationContract,
    Phase9Manifest,
)
from document_engine.evaluation.phase9f import (
    Phase9EvaluationPath,
    Phase9FDocumentObservation,
    Phase9FRunContract,
    aggregate_phase9f_observations,
    build_phase9f_plan,
    validate_private_manifest_files,
)


BASELINE = "2eb4b3f7695ef6693369d732a8520fe243269d7a"
DOCLING = "87c55aff8ac4bdf03ddceab7176344eccb608ea3"
PADDLE = "b02ba775d279802fb92382ed9f564d86c016c152"


def _run_contract(**overrides):
    data = {
        "baseline_revision": BASELINE,
        "docling_semantic_revision": DOCLING,
        "paddle_visual_revision": PADDLE,
    }
    data.update(overrides)
    return Phase9FRunContract(**data)


def _document(alias, family, cohort, layout_group):
    return Phase9DocumentManifestEntry(
        alias=alias,
        family=family,
        cohort=cohort,
        expected_profile=PDFProfileType.NATIVE_PDF,
        layout_group=layout_group,
        source_ref=f"workspace/private/phase9/documents/{alias}.pdf",
        audit_ref=f"workspace/private/phase9/audit/{alias}.audit.json",
    )


def _contract():
    return Phase9EvaluationContract(
        frozen_baseline_revision=BASELINE,
        minimum_documents=3,
        minimum_layout_groups=3,
    )


def _manifest():
    return Phase9Manifest(
        frozen_baseline_revision=BASELINE,
        documents=[
            _document(
                "current-sales",
                DocumentFamilyType.SALES_INVOICE,
                EvaluationCohort.CURRENT_PILOT,
                "layout-a",
            ),
            _document(
                "holdout-utility",
                DocumentFamilyType.UTILITY_CONSUMPTION_INVOICE,
                EvaluationCohort.HOLDOUT_SAME_FAMILY,
                "layout-b",
            ),
            _document(
                "unknown-receipt",
                DocumentFamilyType.RECEIPT,
                EvaluationCohort.UNKNOWN_FAMILY,
                "layout-c",
            ),
        ],
    )


def test_phase9f_run_contract_rejects_oracle_family():
    with pytest.raises(ValueError, match="extraction oracle"):
        _run_contract(allow_oracle_family=True)


def test_phase9f_run_contract_rejects_holdout_tuning():
    with pytest.raises(ValueError, match="holdout tuning"):
        _run_contract(allow_holdout_tuning=True)


def test_phase9f_plan_has_three_independent_paths_per_document():
    plan = build_phase9f_plan(_contract(), _manifest(), _run_contract())

    assert plan.document_count == 3
    assert len(plan.items) == 9
    assert plan.path_counts == {
        Phase9EvaluationPath.A_DETERMINISTIC.value: 3,
        Phase9EvaluationPath.B_DOCLING_SEMANTIC.value: 3,
        Phase9EvaluationPath.C_PADDLE_VISUAL.value: 3,
    }
    assert plan.oracle_family_forbidden is True
    assert plan.holdout_tuning_allowed is False
    assert plan.manual_heavy_execution_only is True


def test_phase9f_semantic_path_uses_classifier_not_expected_family():
    plan = build_phase9f_plan(_contract(), _manifest(), _run_contract())
    semantic_items = [
        item for item in plan.items if item.path == Phase9EvaluationPath.B_DOCLING_SEMANTIC
    ]

    assert len(semantic_items) == 3
    assert all(item.use_expected_family_for_execution is False for item in semantic_items)
    assert all(
        item.semantic_schema_condition_source == "frozen_classifier_output"
        for item in semantic_items
    )
    assert all(item.unsupported_family_policy == "abstain" for item in semantic_items)


def test_phase9f_plan_is_privacy_safe_and_omits_private_refs():
    plan = build_phase9f_plan(_contract(), _manifest(), _run_contract())
    serialized = plan.model_dump_json()

    assert "workspace/private" not in serialized
    assert ".audit.json" not in serialized
    assert ".pdf" not in serialized


def test_phase9_manifest_rejects_path_traversal():
    with pytest.raises(ValueError, match="workspace-relative"):
        Phase9DocumentManifestEntry(
            alias="bad",
            family=DocumentFamilyType.SALES_INVOICE,
            cohort=EvaluationCohort.CURRENT_PILOT,
            layout_group="layout-a",
            source_ref="workspace/private/phase9/../../outside.pdf",
            audit_ref="workspace/private/phase9/audit/bad.audit.json",
        )


def test_validate_private_manifest_files_reports_alias_only(tmp_path: Path):
    manifest = _manifest()
    missing = validate_private_manifest_files(tmp_path, manifest)

    assert missing == [
        "current-sales:source",
        "current-sales:audit",
        "holdout-utility:source",
        "holdout-utility:audit",
        "unknown-receipt:source",
        "unknown-receipt:audit",
    ]
    assert str(tmp_path) not in " ".join(missing)


def test_phase9f_observation_rejects_impossible_grounded_counts():
    with pytest.raises(ValueError, match="Grounded predictions"):
        Phase9FDocumentObservation(
            alias="doc",
            cohort=EvaluationCohort.CURRENT_PILOT,
            path=Phase9EvaluationPath.B_DOCLING_SEMANTIC,
            predicted_family=DocumentFamilyType.SALES_INVOICE,
            predicted_field_count=1,
            grounded_prediction_count=2,
        )


def test_phase9f_aggregation_is_field_weighted_and_resource_safe():
    observations = [
        Phase9FDocumentObservation(
            alias="a",
            cohort=EvaluationCohort.HOLDOUT_SAME_FAMILY,
            path=Phase9EvaluationPath.A_DETERMINISTIC,
            predicted_family=DocumentFamilyType.SALES_INVOICE,
            confirmed_field_count=2,
            predicted_field_count=2,
            exact_match_count=1,
            normalized_match_count=1,
            false_positive_count=1,
            grounded_prediction_count=2,
            grounded_correct_count=1,
            unsupported_prediction_count=0,
            abstained_field_count=0,
            hallucination_count=0,
            table_line_item_expected_count=2,
            table_line_item_match_count=1,
            completeness_score=0.5,
            validation_pass=True,
            review_required=False,
            runtime_seconds=2.0,
            peak_rss_mb=100.0,
        ),
        Phase9FDocumentObservation(
            alias="b",
            cohort=EvaluationCohort.HOLDOUT_SAME_FAMILY,
            path=Phase9EvaluationPath.A_DETERMINISTIC,
            predicted_family=DocumentFamilyType.SALES_INVOICE,
            confirmed_field_count=6,
            predicted_field_count=4,
            exact_match_count=3,
            normalized_match_count=4,
            false_positive_count=0,
            grounded_prediction_count=3,
            grounded_correct_count=3,
            unsupported_prediction_count=1,
            abstained_field_count=2,
            hallucination_count=1,
            table_line_item_expected_count=2,
            table_line_item_match_count=2,
            completeness_score=1.0,
            validation_pass=False,
            review_required=True,
            runtime_seconds=4.0,
            peak_rss_mb=300.0,
        ),
    ]

    summary = aggregate_phase9f_observations(observations)[
        Phase9EvaluationPath.A_DETERMINISTIC.value
    ]

    assert summary.confirmed_field_count == 8
    assert summary.normalized_match_count == 5
    assert summary.metrics["normalized_match"] == pytest.approx(5 / 8)
    assert summary.metrics["prediction_precision"] == pytest.approx(5 / 6)
    assert summary.metrics["evidence_coverage"] == pytest.approx(5 / 6)
    assert summary.metrics["evidence_grounded_precision"] == pytest.approx(4 / 5)
    assert summary.metrics["unsupported_prediction_rate"] == pytest.approx(1 / 6)
    assert summary.metrics["abstention_rate"] == pytest.approx(2 / 8)
    assert summary.metrics["table_line_item_accuracy"] == pytest.approx(3 / 4)
    assert summary.metrics["completeness"] == pytest.approx(0.75)
    assert summary.metrics["validation_pass_rate"] == pytest.approx(0.5)
    assert summary.metrics["review_rate"] == pytest.approx(0.5)
    assert summary.metrics["runtime_seconds"] == pytest.approx(3.0)
    assert summary.metrics["peak_rss_mb"] == pytest.approx(300.0)
    assert summary.metrics["hallucination_count"] == 1.0
