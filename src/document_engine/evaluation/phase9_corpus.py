"""Private corpus registry and readiness evaluation models for Phase 9."""

import hashlib
import json
from pathlib import Path, PurePosixPath
import re
from typing import List, Optional, Tuple

import yaml
from pydantic import BaseModel, Field, field_validator, model_validator

from document_engine.core.models import DocumentFamilyType, PDFProfileType
from document_engine.evaluation.audit_models import FieldAuditStatus
from document_engine.semantic.schema_registry import supports_semantic_schema

VALID_COHORTS = {"current_pilot", "holdout_same_family", "unknown_family"}


def compute_file_sha256(file_path: Path, chunk_size: int = 65536) -> str:
    """Compute SHA256 of a file using chunked/streaming read."""
    hasher = hashlib.sha256()
    with Path(file_path).open("rb") as handle:
        while chunk := handle.read(chunk_size):
            hasher.update(chunk)
    return hasher.hexdigest()


def is_cohort_family_compatible(cohort: str, family: str) -> bool:
    """Check cohort / family semantic alignment.

    - holdout_same_family: family MUST be supported by mature semantic schema registry.
    - unknown_family: family MUST NOT be supported by mature semantic schema registry.
    - current_pilot: allowed for any valid DocumentFamilyType.
    """
    try:
        family_enum = DocumentFamilyType(family)
    except ValueError:
        return False

    is_mature = supports_semantic_schema(family_enum)

    if cohort == "holdout_same_family":
        return is_mature
    if cohort == "unknown_family":
        return not is_mature
    return cohort == "current_pilot"


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

    @field_validator("sha256")
    @classmethod
    def validate_sha256(cls, v: str) -> str:
        if not v or not re.match(r"^[0-9a-fA-F]{64}$", v.strip()):
            raise ValueError("SHA256 must be exactly 64 hexadecimal characters.")
        return v.strip().lower()

    @field_validator("source_ref", "audit_ref")
    @classmethod
    def validate_workspace_relative_ref(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        if Path(value).is_absolute() or re.match(r"^[A-Za-z]:[\\/]", value):
            raise ValueError("Phase 9 private references must use workspace-relative paths.")

        normalized = value.replace("\\", "/")
        parts = PurePosixPath(normalized).parts
        if ".." in parts or not parts or parts[0] != "workspace":
            raise ValueError("Phase 9 private references must use workspace-relative paths starting with workspace/.")
        return normalized

    @field_validator("cohort")
    @classmethod
    def validate_cohort(cls, v: str) -> str:
        if v not in VALID_COHORTS:
            raise ValueError(f"Invalid cohort '{v}'. Must be one of {sorted(VALID_COHORTS)}")
        return v

    @field_validator("family")
    @classmethod
    def validate_family(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Family must not be empty.")
        valid_families = {item.value for item in DocumentFamilyType}
        if v.strip() not in valid_families:
            raise ValueError(f"Invalid DocumentFamilyType '{v}'. Must be one of {sorted(valid_families)}")
        return v.strip()

    @field_validator("expected_profile")
    @classmethod
    def validate_expected_profile(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        valid_profiles = {item.value for item in PDFProfileType}
        if v.strip() not in valid_profiles:
            raise ValueError(f"Invalid PDFProfileType '{v}'. Must be one of {sorted(valid_profiles)}")
        return v.strip()

    @field_validator("alias", "layout_group")
    @classmethod
    def validate_non_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Field must not be empty.")
        return v.strip()


class Phase9CorpusRegistry(BaseModel):
    """Registry container storing all candidate document metadata."""

    registry_version: str = "1.0"
    candidates: List[Phase9CorpusCandidate] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_unique_aliases(self) -> "Phase9CorpusRegistry":
        aliases = [c.alias for c in self.candidates]
        if len(aliases) != len(set(aliases)):
            raise ValueError("Phase 9 registry candidate aliases must be unique.")
        return self

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

    STRICT CONTRACT: Only fields with status == FieldAuditStatus.CONFIRMED
    increment the confirmed_field_count.

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

    for fval in fields.values():
        if isinstance(fval, dict):
            status = str(fval.get("status", "")).strip()
            if status == FieldAuditStatus.CONFIRMED.value:
                confirmed_count += 1
        elif fval is not None:
            # Scalar value without status dict does NOT count under strict contract
            pass

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
    documents_without_confirmed_fields: int = 0
    missing_audit_count: int = 0
    missing_family_count: int = 0
    missing_layout_group_count: int = 0
    prior_tuning_holdout_rejections: int = 0
    cohort_family_mismatch_count: int = 0
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
        )
        return self


def select_evaluation_ready_candidates(
    registry: Phase9CorpusRegistry,
    base_dir: Path = Path("."),
    minimum_documents: int = 12,
    minimum_layout_groups: int = 4,
) -> Tuple[List[Phase9CorpusCandidate], Phase9CorpusReadinessReport]:
    """Deterministically select evaluation-ready candidates and compute readiness summary."""
    registered = len(registry.candidates)
    seen_shas = set()
    duplicate_count = 0

    eligible_candidates: List[Phase9CorpusCandidate] = []
    eligible_layout_groups = set()

    pilot_count = 0
    holdout_count = 0
    unknown_count = 0

    docs_with_audit = 0
    docs_with_confirmed = 0
    docs_without_confirmed = 0
    missing_audit = 0
    missing_family = 0
    missing_layout = 0
    holdout_rejections = 0
    mismatch_count = 0

    valid_families = {item.value for item in DocumentFamilyType}

    for cand in registry.candidates:
        is_duplicate = False
        sha_lower = cand.sha256.lower()
        if sha_lower in seen_shas:
            duplicate_count += 1
            is_duplicate = True
        else:
            seen_shas.add(sha_lower)

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
                docs_without_confirmed += 1
        else:
            missing_audit += 1

        family_valid = bool(cand.family and cand.family in valid_families)
        if not family_valid:
            missing_family += 1

        layout_valid = bool(cand.layout_group and cand.layout_group != "LAYOUT_GROUP_METADATA_MISSING")
        if not layout_valid:
            missing_layout += 1

        holdout_rejected = cand.cohort == "holdout_same_family" and cand.used_for_prior_tuning
        if holdout_rejected:
            holdout_rejections += 1

        cohort_mismatch = not is_cohort_family_compatible(cand.cohort, cand.family)
        if cohort_mismatch:
            mismatch_count += 1

        # EVALUATION-READY CANDIDATE CONTRACT:
        # Requires source_exists, audit_exists AND confirmed_count > 0, family_valid, layout_valid,
        # not duplicate, not prior-tuned holdout, and cohort/family semantic match.
        is_eligible = (
            source_exists
            and audit_exists
            and confirmed_count > 0
            and family_valid
            and layout_valid
            and not is_duplicate
            and not holdout_rejected
            and not cohort_mismatch
        )

        if is_eligible:
            eligible_candidates.append(cand)
            eligible_layout_groups.add(cand.layout_group)
            if cand.cohort == "current_pilot":
                pilot_count += 1
            elif cand.cohort == "holdout_same_family":
                holdout_count += 1
            elif cand.cohort == "unknown_family":
                unknown_count += 1

    report = Phase9CorpusReadinessReport(
        registered_documents=registered,
        eligible_documents=len(eligible_candidates),
        current_pilot_count=pilot_count,
        holdout_same_family_count=holdout_count,
        unknown_family_count=unknown_count,
        distinct_layout_groups=len(eligible_layout_groups),
        documents_with_audit=docs_with_audit,
        documents_with_confirmed_audit=docs_with_confirmed,
        documents_without_confirmed_fields=docs_without_confirmed,
        missing_audit_count=missing_audit,
        missing_family_count=missing_family,
        missing_layout_group_count=missing_layout,
        prior_tuning_holdout_rejections=holdout_rejections,
        cohort_family_mismatch_count=mismatch_count,
        duplicate_count=duplicate_count,
        minimum_documents=minimum_documents,
        minimum_layout_groups=minimum_layout_groups,
    )

    return eligible_candidates, report


def evaluate_corpus_readiness(
    registry: Phase9CorpusRegistry,
    base_dir: Path = Path("."),
    minimum_documents: int = 12,
    minimum_layout_groups: int = 4,
) -> Phase9CorpusReadinessReport:
    """Evaluate registry candidates against Phase 9 readiness requirements."""
    _, report = select_evaluation_ready_candidates(
        registry,
        base_dir=base_dir,
        minimum_documents=minimum_documents,
        minimum_layout_groups=minimum_layout_groups,
    )
    return report
