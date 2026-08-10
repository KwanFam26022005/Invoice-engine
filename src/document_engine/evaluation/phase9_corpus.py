"""Private corpus registry and readiness evaluation models for Phase 9."""

import json
from pathlib import Path
from typing import List, Optional, Tuple

import yaml
from pydantic import BaseModel, Field, field_validator, model_validator


VALID_COHORTS = {"current_pilot", "holdout_same_family", "unknown_family"}


class Phase9CorpusCandidate(BaseModel):
    """Metadata container for a registered private corpus candidate document."""

    alias: str
    source_ref: str
    audit_ref: Optional[str] = None
    family: str
    cohort: str
    expected_profile: Optional[str] = None
    layout_group: str
    sha256: str
    used_for_prior_tuning: bool = False
    audit_confirmed_field_count: int = 0

    @field_validator("source_ref", "audit_ref")
    @classmethod
    def validate_workspace_relative_path(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        p = Path(v)
        if p.is_absolute():
            raise ValueError(f"Path must be workspace-relative, got absolute path: {v}")
        parts = p.parts
        if ".." in parts:
            raise ValueError(f"Path must not contain parent directory traversal ('..'): {v}")
        return v

    @field_validator("cohort")
    @classmethod
    def validate_cohort(cls, v: str) -> str:
        if v not in VALID_COHORTS:
            raise ValueError(f"Invalid cohort '{v}'. Must be one of {sorted(VALID_COHORTS)}")
        return v

    @field_validator("alias", "family", "layout_group")
    @classmethod
    def validate_non_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Field must not be empty.")
        return v.strip()


class Phase9CorpusRegistry(BaseModel):
    """Registry container storing all candidate document metadata."""

    registry_version: str = "1.0"
    candidates: List[Phase9CorpusCandidate] = Field(default_factory=list)

    @classmethod
    def load_yaml(cls, path: Path) -> "Phase9CorpusRegistry":
        p = Path(path)
        if not p.exists():
            return cls()
        data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        return cls.model_validate(data)

    def save_yaml(self, path: Path) -> None:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        dump_data = self.model_dump(mode="json")
        p.write_text(yaml.safe_dump(dump_data, sort_keys=False), encoding="utf-8")

    def find_by_alias(self, alias: str) -> Optional[Phase9CorpusCandidate]:
        for c in self.candidates:
            if c.alias == alias:
                return c
        return None

    def find_by_sha256(self, sha256: str) -> Optional[Phase9CorpusCandidate]:
        for c in self.candidates:
            if c.sha256.lower() == sha256.lower():
                return c
        return None

    def add_or_update_candidate(self, candidate: Phase9CorpusCandidate) -> None:
        for i, c in enumerate(self.candidates):
            if c.alias == candidate.alias:
                self.candidates[i] = candidate
                return
        self.candidates.append(candidate)


def count_audit_confirmed_fields(audit_path: Path) -> Tuple[bool, int]:
    """Inspect private audit JSON without exposing expected values or text.

    Returns:
        (audit_exists, confirmed_field_count)
    """
    p = Path(audit_path)
    if not p.exists() or not p.is_file():
        return False, 0

    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return True, 0

    fields = data.get("fields", {})
    if not isinstance(fields, dict):
        return True, 0

    confirmed_count = 0
    confirmed_statuses = {"CONFIRMED", "audited", "confirmed", "valid", "ok", "user_confirmed"}

    for fval in fields.values():
        if isinstance(fval, dict):
            status = str(fval.get("status", "")).strip()
            if status in confirmed_statuses or (
                "expected" in fval and fval["expected"] is not None and status not in {"NOT_AUDITED", "UNCONFIRMED"}
            ):
                confirmed_count += 1
        elif fval is not None:
            confirmed_count += 1

    return True, confirmed_count


class Phase9CorpusReadinessReport(BaseModel):
    """Summary metrics of private corpus readiness."""

    registered_documents: int = 0
    eligible_documents: int = 0
    current_pilot_count: int = 0
    holdout_same_family_count: int = 0
    unknown_family_count: int = 0
    distinct_layout_groups: int = 0
    documents_with_audit: int = 0
    documents_with_confirmed_audit: int = 0
    missing_audit_count: int = 0
    missing_family_count: int = 0
    missing_layout_group_count: int = 0
    prior_tuning_holdout_rejections: int = 0
    duplicate_count: int = 0
    minimum_documents: int = 12
    minimum_layout_groups: int = 4
    remaining_document_deficit: int = 12
    is_ready: bool = False

    @model_validator(mode="after")
    def compute_derived_status(self) -> "Phase9CorpusReadinessReport":
        required_cohorts_present = (
            self.current_pilot_count > 0 and self.holdout_same_family_count > 0 and self.unknown_family_count > 0
        )
        self.remaining_document_deficit = max(0, self.minimum_documents - self.eligible_documents)
        self.is_ready = (
            self.eligible_documents >= self.minimum_documents
            and self.distinct_layout_groups >= self.minimum_layout_groups
            and required_cohorts_present
            and self.missing_audit_count == 0
            and self.missing_family_count == 0
            and self.missing_layout_group_count == 0
        )
        return self


def evaluate_corpus_readiness(
    registry: Phase9CorpusRegistry,
    base_dir: Path = Path("."),
    minimum_documents: int = 12,
    minimum_layout_groups: int = 4,
) -> Phase9CorpusReadinessReport:
    """Evaluate registry candidates against Phase 9 readiness requirements."""
    registered = len(registry.candidates)
    eligible_candidates: List[Phase9CorpusCandidate] = []

    pilot_count = 0
    holdout_count = 0
    unknown_count = 0
    layout_groups = set()
    docs_with_audit = 0
    docs_with_confirmed = 0
    missing_audit = 0
    missing_family = 0
    missing_layout = 0
    holdout_rejections = 0

    for cand in registry.candidates:
        source_path = base_dir / cand.source_ref
        source_exists = source_path.exists() and source_path.is_file()

        audit_exists = False
        confirmed_count = cand.audit_confirmed_field_count

        if cand.audit_ref:
            audit_path = base_dir / cand.audit_ref
            audit_exists, count_from_file = count_audit_confirmed_fields(audit_path)
            if audit_exists:
                confirmed_count = count_from_file

        if audit_exists:
            docs_with_audit += 1
            if confirmed_count > 0:
                docs_with_confirmed += 1
        else:
            missing_audit += 1

        if not cand.family or cand.family == "FAMILY_METADATA_MISSING":
            missing_family += 1

        if not cand.layout_group or cand.layout_group == "LAYOUT_GROUP_METADATA_MISSING":
            missing_layout += 1
        else:
            layout_groups.add(cand.layout_group)

        # Holdout safety check
        if cand.cohort == "holdout_same_family" and cand.used_for_prior_tuning:
            holdout_rejections += 1
            continue

        is_eligible = (
            source_exists
            and audit_exists
            and bool(cand.family and cand.family != "FAMILY_METADATA_MISSING")
            and bool(cand.layout_group and cand.layout_group != "LAYOUT_GROUP_METADATA_MISSING")
        )

        if is_eligible:
            eligible_candidates.append(cand)
            if cand.cohort == "current_pilot":
                pilot_count += 1
            elif cand.cohort == "holdout_same_family":
                holdout_count += 1
            elif cand.cohort == "unknown_family":
                unknown_count += 1

    return Phase9CorpusReadinessReport(
        registered_documents=registered,
        eligible_documents=len(eligible_candidates),
        current_pilot_count=pilot_count,
        holdout_same_family_count=holdout_count,
        unknown_family_count=unknown_count,
        distinct_layout_groups=len(layout_groups),
        documents_with_audit=docs_with_audit,
        documents_with_confirmed_audit=docs_with_confirmed,
        missing_audit_count=missing_audit,
        missing_family_count=missing_family,
        missing_layout_group_count=missing_layout,
        prior_tuning_holdout_rejections=holdout_rejections,
        duplicate_count=0,
        minimum_documents=minimum_documents,
        minimum_layout_groups=minimum_layout_groups,
    )
