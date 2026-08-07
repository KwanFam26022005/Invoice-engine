"""Tests for Phase 9 evaluation and generalization contracts."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from document_engine.evaluation.phase9_contract import (
    EvaluationCohort,
    Phase9EvaluationContract,
    Phase9Manifest,
    Phase9Metric,
)


BASELINE = "2eb4b3f7695ef6693369d732a8520fe243269d7a"


def test_phase9_tracked_contract_loads_and_locks_holdout():
    contract = Phase9EvaluationContract.load_yaml(
        Path("configs/evaluation/phase9_schema.yaml")
    )

    assert contract.frozen_baseline_revision == BASELINE
    assert contract.holdout_locked_before_engine_canary is True
    assert contract.allow_holdout_tuning is False
    assert Phase9Metric.UNSUPPORTED_PREDICTION_RATE in contract.required_metrics
    assert Phase9Metric.ABSTENTION_RATE in contract.required_metrics
    assert Phase9Metric.EVIDENCE_GROUNDED_PRECISION in contract.required_metrics


def test_phase9_example_manifest_covers_required_cohorts_and_layouts():
    contract = Phase9EvaluationContract.load_yaml(
        Path("configs/evaluation/phase9_schema.yaml")
    )
    manifest = Phase9Manifest.load_yaml(
        Path("configs/evaluation/phase9_manifest.example.yaml")
    )

    contract.validate_manifest(manifest)

    assert {item.cohort for item in manifest.documents} == {
        EvaluationCohort.CURRENT_PILOT,
        EvaluationCohort.HOLDOUT_SAME_FAMILY,
        EvaluationCohort.UNKNOWN_FAMILY,
    }


def test_phase9_contract_rejects_holdout_tuning():
    with pytest.raises(ValidationError):
        Phase9EvaluationContract(
            frozen_baseline_revision=BASELINE,
            allow_holdout_tuning=True,
        )


def test_phase9_manifest_rejects_duplicate_aliases():
    duplicate = {
        "manifest_version": "1.0",
        "frozen_baseline_revision": BASELINE,
        "documents": [
            {
                "alias": "same",
                "family": "sales_invoice",
                "cohort": "current_pilot",
                "layout_group": "sales_a",
                "source_ref": "workspace/private/phase9/documents/a.pdf",
                "audit_ref": "workspace/private/phase9/audit/a.audit.json",
            },
            {
                "alias": "same",
                "family": "sales_invoice",
                "cohort": "holdout_same_family",
                "layout_group": "sales_b",
                "source_ref": "workspace/private/phase9/documents/b.pdf",
                "audit_ref": "workspace/private/phase9/audit/b.audit.json",
            },
        ],
    }

    with pytest.raises(ValidationError):
        Phase9Manifest.model_validate(duplicate)
