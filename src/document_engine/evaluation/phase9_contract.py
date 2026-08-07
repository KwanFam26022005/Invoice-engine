"""Phase 9 generalization and evaluation contracts.

The contract is intentionally independent from private pilot files. It defines
how holdout documents are grouped and which metrics must be reported before any
semantic engine canary is compared with the frozen R3 baseline.
"""

from enum import Enum
from pathlib import Path
import re
from typing import List, Optional

import yaml
from pydantic import BaseModel, Field, field_validator, model_validator

from document_engine.core.models import DocumentFamilyType, PDFProfileType


class EvaluationCohort(str, Enum):
    CURRENT_PILOT = "current_pilot"
    HOLDOUT_SAME_FAMILY = "holdout_same_family"
    UNKNOWN_FAMILY = "unknown_family"


class Phase9Metric(str, Enum):
    EXACT_MATCH = "exact_match"
    NORMALIZED_MATCH = "normalized_match"
    PREDICTION_PRECISION = "prediction_precision"
    PREDICTION_RECALL = "prediction_recall"
    EVIDENCE_COVERAGE = "evidence_coverage"
    EVIDENCE_GROUNDED_PRECISION = "evidence_grounded_precision"
    UNSUPPORTED_PREDICTION_RATE = "unsupported_prediction_rate"
    ABSTENTION_RATE = "abstention_rate"
    HALLUCINATION_COUNT = "hallucination_count"
    TABLE_LINE_ITEM_ACCURACY = "table_line_item_accuracy"
    COMPLETENESS = "completeness"
    VALIDATION_PASS_RATE = "validation_pass_rate"
    REVIEW_RATE = "review_rate"
    RUNTIME_SECONDS = "runtime_seconds"
    PEAK_RSS_MB = "peak_rss_mb"


class Phase9DocumentManifestEntry(BaseModel):
    alias: str = Field(min_length=1)
    family: DocumentFamilyType
    cohort: EvaluationCohort
    expected_profile: Optional[PDFProfileType] = None
    layout_group: str = Field(min_length=1)
    source_ref: str = Field(
        min_length=1,
        description="Opaque or workspace-relative source reference; never an absolute private path.",
    )
    audit_ref: str = Field(
        min_length=1,
        description="Workspace-relative audit reference; private values remain outside git.",
    )

    @field_validator("source_ref", "audit_ref")
    @classmethod
    def validate_private_relative_ref(cls, value: str) -> str:
        if Path(value).is_absolute() or re.match(r"^[A-Za-z]:[\\/]", value):
            raise ValueError("Phase 9 private references must not use absolute paths.")
        return value


class Phase9Manifest(BaseModel):
    manifest_version: str = "1.0"
    frozen_baseline_revision: str
    documents: List[Phase9DocumentManifestEntry] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_unique_aliases(self) -> "Phase9Manifest":
        aliases = [item.alias for item in self.documents]
        if len(aliases) != len(set(aliases)):
            raise ValueError("Phase 9 manifest document aliases must be unique.")
        return self

    @classmethod
    def load_yaml(cls, path: Path) -> "Phase9Manifest":
        data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
        return cls.model_validate(data)


class Phase9EvaluationContract(BaseModel):
    contract_version: str = "1.0"
    frozen_baseline_revision: str
    minimum_documents: int = Field(default=12, ge=1)
    target_document_range: str = "12-20"
    minimum_layout_groups: int = Field(default=4, ge=1)
    required_cohorts: List[EvaluationCohort] = Field(
        default_factory=lambda: [
            EvaluationCohort.CURRENT_PILOT,
            EvaluationCohort.HOLDOUT_SAME_FAMILY,
            EvaluationCohort.UNKNOWN_FAMILY,
        ]
    )
    required_metrics: List[Phase9Metric] = Field(default_factory=lambda: list(Phase9Metric))
    holdout_locked_before_engine_canary: bool = True
    allow_holdout_tuning: bool = False
    prefer_abstention_over_unsupported_prediction: bool = True
    private_values_must_remain_outside_git: bool = True

    @model_validator(mode="after")
    def validate_safety_contract(self) -> "Phase9EvaluationContract":
        if self.allow_holdout_tuning:
            raise ValueError("Phase 9 holdout tuning must remain disabled.")
        if not self.holdout_locked_before_engine_canary:
            raise ValueError("Phase 9 holdout must be locked before engine canaries.")
        if not self.private_values_must_remain_outside_git:
            raise ValueError("Private evaluation values must remain outside git.")
        return self

    @classmethod
    def load_yaml(cls, path: Path) -> "Phase9EvaluationContract":
        data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
        return cls.model_validate(data)

    def validate_manifest(self, manifest: Phase9Manifest) -> None:
        if manifest.frozen_baseline_revision != self.frozen_baseline_revision:
            raise ValueError("Manifest baseline revision does not match evaluation contract.")

        if len(manifest.documents) < self.minimum_documents:
            raise ValueError(
                f"Phase 9 manifest requires at least {self.minimum_documents} documents."
            )

        cohorts = {item.cohort for item in manifest.documents}
        missing = set(self.required_cohorts) - cohorts
        if missing:
            missing_values = ", ".join(sorted(item.value for item in missing))
            raise ValueError(f"Phase 9 manifest is missing required cohorts: {missing_values}")

        layout_groups = {item.layout_group for item in manifest.documents}
        if len(layout_groups) < self.minimum_layout_groups:
            raise ValueError(
                "Phase 9 manifest does not contain enough distinct layout groups."
            )
