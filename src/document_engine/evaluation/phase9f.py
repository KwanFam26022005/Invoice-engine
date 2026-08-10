"""Phase 9F controlled A/B/C evaluation planning and privacy-safe aggregation.

This module deliberately does not execute heavyweight parser or VLM inference.
It locks the comparison contract, produces a privacy-safe execution plan, and
aggregates count-only observations produced by later manual path runners.
"""

from __future__ import annotations

from enum import Enum
from hashlib import sha256
import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

import yaml
from pydantic import BaseModel, Field, model_validator

from document_engine.core.models import DocumentFamilyType
from document_engine.evaluation.phase9_contract import (
    EvaluationCohort,
    Phase9EvaluationContract,
    Phase9Manifest,
)


class Phase9EvaluationPath(str, Enum):
    A_DETERMINISTIC = "a_deterministic"
    B_DOCLING_SEMANTIC = "b_docling_semantic"
    C_PADDLE_VISUAL = "c_paddle_visual"


class Phase9FRunContract(BaseModel):
    """Frozen component revisions and fairness rules for Phase 9F."""

    contract_version: str = "1.0"
    baseline_revision: str = Field(min_length=7)
    docling_semantic_revision: str = Field(min_length=7)
    paddle_visual_revision: str = Field(min_length=7)
    allow_oracle_family: bool = False
    allow_holdout_tuning: bool = False
    require_independent_paths: bool = True
    manual_heavy_execution_only: bool = True
    schema_condition_source: str = "frozen_classifier_output"
    unknown_family_semantic_policy: str = "abstain"

    @model_validator(mode="after")
    def validate_fairness(self) -> Phase9FRunContract:
        if self.allow_oracle_family:
            raise ValueError("Phase 9F must not use audited/expected family as an extraction oracle.")
        if self.allow_holdout_tuning:
            raise ValueError("Phase 9F holdout tuning must remain disabled.")
        if not self.require_independent_paths:
            raise ValueError("Phase 9F paths must remain independent before the hybrid phase.")
        if not self.manual_heavy_execution_only:
            raise ValueError("Phase 9F heavyweight inference must remain an explicit manual gate.")
        if self.schema_condition_source != "frozen_classifier_output":
            raise ValueError("Docling semantic schema conditioning must use frozen classifier output.")
        if self.unknown_family_semantic_policy != "abstain":
            raise ValueError("Unsupported semantic families must abstain during Phase 9F.")
        return self

    @classmethod
    def load_yaml(cls, path: Path) -> Phase9FRunContract:
        data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
        return cls.model_validate(data)

    def validate_against_phase9(self, contract: Phase9EvaluationContract) -> None:
        if self.baseline_revision != contract.frozen_baseline_revision:
            raise ValueError("Phase 9F baseline revision does not match the Phase 9 contract.")
        if contract.allow_holdout_tuning:
            raise ValueError("Phase 9 evaluation contract unexpectedly permits holdout tuning.")

    def revision_for_path(self, path: Phase9EvaluationPath) -> str:
        if path == Phase9EvaluationPath.A_DETERMINISTIC:
            return self.baseline_revision
        if path == Phase9EvaluationPath.B_DOCLING_SEMANTIC:
            return self.docling_semantic_revision
        return self.paddle_visual_revision


class Phase9FPlanItem(BaseModel):
    alias: str
    cohort: EvaluationCohort
    layout_group: str
    manifest_family: DocumentFamilyType
    path: Phase9EvaluationPath
    frozen_revision: str
    heavy_execution: bool = True
    use_expected_family_for_execution: bool = False
    semantic_schema_condition_source: Optional[str] = None
    unsupported_family_policy: Optional[str] = None


class Phase9FExecutionPlan(BaseModel):
    plan_version: str = "1.0"
    fingerprint: str
    baseline_revision: str
    document_count: int
    layout_group_count: int
    cohort_counts: Dict[str, int]
    path_counts: Dict[str, int]
    required_metrics: List[str]
    oracle_family_forbidden: bool = True
    holdout_tuning_allowed: bool = False
    manual_heavy_execution_only: bool = True
    items: List[Phase9FPlanItem] = Field(default_factory=list)


class Phase9FDocumentObservation(BaseModel):
    """Privacy-safe count-only observation for one document/path execution.

    No extracted field value, source text, filename, source path, or audit value is
    permitted in this model. Later execution code must reduce private comparisons
    to counts before persisting a Phase 9F observation.
    """

    alias: str
    cohort: EvaluationCohort
    path: Phase9EvaluationPath
    predicted_family: DocumentFamilyType
    family_match: Optional[bool] = None

    confirmed_field_count: int = Field(default=0, ge=0)
    predicted_field_count: int = Field(default=0, ge=0)
    exact_match_count: int = Field(default=0, ge=0)
    normalized_match_count: int = Field(default=0, ge=0)
    false_positive_count: int = Field(default=0, ge=0)
    grounded_prediction_count: int = Field(default=0, ge=0)
    grounded_correct_count: int = Field(default=0, ge=0)
    unsupported_prediction_count: int = Field(default=0, ge=0)
    abstained_field_count: int = Field(default=0, ge=0)
    hallucination_count: int = Field(default=0, ge=0)

    table_line_item_expected_count: int = Field(default=0, ge=0)
    table_line_item_match_count: int = Field(default=0, ge=0)

    completeness_score: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    validation_pass: Optional[bool] = None
    review_required: Optional[bool] = None
    runtime_seconds: Optional[float] = Field(default=None, ge=0.0)
    peak_rss_mb: Optional[float] = Field(default=None, ge=0.0)

    @model_validator(mode="after")
    def validate_counts(self) -> Phase9FDocumentObservation:
        if self.exact_match_count > self.confirmed_field_count:
            raise ValueError("Exact matches cannot exceed confirmed audited fields.")
        if self.normalized_match_count > self.confirmed_field_count:
            raise ValueError("Normalized matches cannot exceed confirmed audited fields.")
        if self.grounded_prediction_count > self.predicted_field_count:
            raise ValueError("Grounded predictions cannot exceed predictions.")
        if self.grounded_correct_count > self.grounded_prediction_count:
            raise ValueError("Grounded correct predictions cannot exceed grounded predictions.")
        if self.unsupported_prediction_count > self.predicted_field_count:
            raise ValueError("Unsupported predictions cannot exceed predictions.")
        if self.table_line_item_match_count > self.table_line_item_expected_count:
            raise ValueError("Matched line items cannot exceed expected line items.")
        return self


class Phase9FPathSummary(BaseModel):
    path: Phase9EvaluationPath
    document_count: int
    confirmed_field_count: int
    predicted_field_count: int
    exact_match_count: int
    normalized_match_count: int
    false_positive_count: int
    grounded_prediction_count: int
    grounded_correct_count: int
    unsupported_prediction_count: int
    abstained_field_count: int
    hallucination_count: int
    table_line_item_expected_count: int
    table_line_item_match_count: int
    metrics: Dict[str, Optional[float]]


def _rate(numerator: int, denominator: int) -> Optional[float]:
    if denominator <= 0:
        return None
    return numerator / denominator


def _mean(values: Iterable[Optional[float]]) -> Optional[float]:
    present = [value for value in values if value is not None]
    if not present:
        return None
    return sum(present) / len(present)


def _bool_rate(values: Iterable[Optional[bool]], target: bool) -> Optional[float]:
    present = [value for value in values if value is not None]
    if not present:
        return None
    return sum(value is target for value in present) / len(present)


def build_phase9f_plan(
    contract: Phase9EvaluationContract,
    manifest: Phase9Manifest,
    run_contract: Phase9FRunContract,
) -> Phase9FExecutionPlan:
    """Validate and lock a three-path plan without touching private document bytes."""

    contract.validate_manifest(manifest)
    run_contract.validate_against_phase9(contract)

    items: List[Phase9FPlanItem] = []
    paths = list(Phase9EvaluationPath)
    for document in manifest.documents:
        for path in paths:
            semantic_source = None
            unsupported_policy = None
            if path == Phase9EvaluationPath.B_DOCLING_SEMANTIC:
                semantic_source = run_contract.schema_condition_source
                unsupported_policy = run_contract.unknown_family_semantic_policy
            items.append(
                Phase9FPlanItem(
                    alias=document.alias,
                    cohort=document.cohort,
                    layout_group=document.layout_group,
                    manifest_family=document.family,
                    path=path,
                    frozen_revision=run_contract.revision_for_path(path),
                    heavy_execution=True,
                    use_expected_family_for_execution=False,
                    semantic_schema_condition_source=semantic_source,
                    unsupported_family_policy=unsupported_policy,
                )
            )

    structural_payload = {
        "manifest_version": manifest.manifest_version,
        "baseline_revision": manifest.frozen_baseline_revision,
        "run_contract": run_contract.model_dump(mode="json"),
        "documents": [
            {
                "alias": item.alias,
                "family": item.family.value,
                "cohort": item.cohort.value,
                "layout_group": item.layout_group,
                "expected_profile": item.expected_profile.value
                if item.expected_profile
                else None,
            }
            for item in manifest.documents
        ],
        "required_metrics": [metric.value for metric in contract.required_metrics],
    }
    fingerprint = sha256(
        json.dumps(structural_payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()

    cohort_counts: Dict[str, int] = {}
    for document in manifest.documents:
        cohort_counts[document.cohort.value] = cohort_counts.get(document.cohort.value, 0) + 1

    return Phase9FExecutionPlan(
        fingerprint=fingerprint,
        baseline_revision=contract.frozen_baseline_revision,
        document_count=len(manifest.documents),
        layout_group_count=len({item.layout_group for item in manifest.documents}),
        cohort_counts=cohort_counts,
        path_counts={path.value: len(manifest.documents) for path in paths},
        required_metrics=[metric.value for metric in contract.required_metrics],
        items=items,
    )


def validate_private_manifest_files(repo_root: Path, manifest: Phase9Manifest) -> List[str]:
    """Return alias/type labels for missing private refs without exposing host paths."""

    root = Path(repo_root).resolve()
    missing: List[str] = []
    for document in manifest.documents:
        for label, relative_ref in (
            ("source", document.source_ref),
            ("audit", document.audit_ref),
        ):
            resolved = (root / relative_ref).resolve()
            if resolved != root and root not in resolved.parents:
                raise ValueError("Private Phase 9 reference escaped repository root.")
            if not resolved.is_file():
                missing.append(f"{document.alias}:{label}")
    return missing


def aggregate_phase9f_observations(
    observations: Iterable[Phase9FDocumentObservation],
) -> Dict[str, Phase9FPathSummary]:
    """Aggregate privacy-safe observations using field-weighted accuracy metrics."""

    grouped: Dict[Phase9EvaluationPath, List[Phase9FDocumentObservation]] = {
        path: [] for path in Phase9EvaluationPath
    }
    for observation in observations:
        grouped[observation.path].append(observation)

    summaries: Dict[str, Phase9FPathSummary] = {}
    for path, rows in grouped.items():
        if not rows:
            continue

        confirmed = sum(row.confirmed_field_count for row in rows)
        predicted = sum(row.predicted_field_count for row in rows)
        exact = sum(row.exact_match_count for row in rows)
        normalized = sum(row.normalized_match_count for row in rows)
        false_positive = sum(row.false_positive_count for row in rows)
        grounded = sum(row.grounded_prediction_count for row in rows)
        grounded_correct = sum(row.grounded_correct_count for row in rows)
        unsupported = sum(row.unsupported_prediction_count for row in rows)
        abstained = sum(row.abstained_field_count for row in rows)
        hallucinations = sum(row.hallucination_count for row in rows)
        table_expected = sum(row.table_line_item_expected_count for row in rows)
        table_match = sum(row.table_line_item_match_count for row in rows)

        metrics: Dict[str, Optional[float]] = {
            "exact_match": _rate(exact, confirmed),
            "normalized_match": _rate(normalized, confirmed),
            "prediction_precision": _rate(normalized, normalized + false_positive),
            "prediction_recall": _rate(normalized, confirmed),
            "evidence_coverage": _rate(grounded, predicted),
            "evidence_grounded_precision": _rate(grounded_correct, grounded),
            "unsupported_prediction_rate": _rate(unsupported, predicted),
            "abstention_rate": _rate(abstained, confirmed),
            "hallucination_count": float(hallucinations),
            "table_line_item_accuracy": _rate(table_match, table_expected),
            "completeness": _mean(row.completeness_score for row in rows),
            "validation_pass_rate": _bool_rate(
                (row.validation_pass for row in rows), target=True
            ),
            "review_rate": _bool_rate((row.review_required for row in rows), target=True),
            "runtime_seconds": _mean(row.runtime_seconds for row in rows),
            "peak_rss_mb": max(
                (row.peak_rss_mb for row in rows if row.peak_rss_mb is not None),
                default=None,
            ),
        }

        summaries[path.value] = Phase9FPathSummary(
            path=path,
            document_count=len(rows),
            confirmed_field_count=confirmed,
            predicted_field_count=predicted,
            exact_match_count=exact,
            normalized_match_count=normalized,
            false_positive_count=false_positive,
            grounded_prediction_count=grounded,
            grounded_correct_count=grounded_correct,
            unsupported_prediction_count=unsupported,
            abstained_field_count=abstained,
            hallucination_count=hallucinations,
            table_line_item_expected_count=table_expected,
            table_line_item_match_count=table_match,
            metrics=metrics,
        )

    return summaries


def execute_phase9f_path_a_observation(
    alias: str,
    repo_root: Path = Path("."),
    manifest_path: str = "workspace/private/phase9/phase9_manifest.yaml",
) -> tuple[Phase9FDocumentObservation, Dict[str, Any]]:
    """Execute Path A for a single manifest candidate alias in a privacy-safe manner."""
    import os
    import time

    from document_engine.core.field_paths import parse_field_path
    from document_engine.evaluation.audit_models import DocumentAuditSpec, FieldAuditStatus
    from document_engine.evaluation.metrics import Evaluator
    from document_engine.orchestration.pipeline import DocumentPipeline
    from document_engine.settings import AppConfig

    root = Path(repo_root).resolve()
    manifest_file = root / manifest_path
    if not manifest_file.exists():
        raise FileNotFoundError(f"Manifest file not found: {manifest_file}")

    manifest = Phase9Manifest.load_yaml(manifest_file)
    cand = next((d for d in manifest.documents if d.alias == alias), None)
    if not cand:
        raise ValueError(f"Candidate '{alias}' not found in manifest.")

    source_pdf = (root / cand.source_ref).resolve()
    audit_json = (root / cand.audit_ref).resolve()

    if not source_pdf.is_file() or not audit_json.is_file():
        raise FileNotFoundError(f"Source PDF or audit JSON missing for '{alias}'.")

    audit_spec = DocumentAuditSpec.model_validate_json(
        audit_json.read_text(encoding="utf-8")
    )

    # Field path syntax validation
    for f_path, entry in audit_spec.fields.items():
        if entry.status == FieldAuditStatus.CONFIRMED:
            parse_field_path(f_path)

    start_time = time.perf_counter()
    peak_rss_mb = None
    try:
        import psutil
        process = psutil.Process(os.getpid())
        peak_rss_mb = process.memory_info().rss / (1024 * 1024)
    except Exception:
        pass

    config = AppConfig(
        default_parser_policy={
            "native_pdf": "pymupdf_native",
            "scan_pdf": "pymupdf_native",
            "mixed_pdf": "pymupdf_native",
            "fallback": "pymupdf_native",
        },
        fallback_enabled=False,
    )

    pipeline = DocumentPipeline(config=config)
    pipeline_res = pipeline.process_file(source_pdf)

    end_time = time.perf_counter()
    runtime_seconds = end_time - start_time

    if peak_rss_mb is not None:
        try:
            import psutil
            process = psutil.Process(os.getpid())
            peak_rss_mb = max(peak_rss_mb, process.memory_info().rss / (1024 * 1024))
        except Exception:
            pass

    evaluator = Evaluator()
    doc_summary = evaluator.evaluate_document(pipeline_res, audit_spec)

    pred_family = DocumentFamilyType(pipeline_res.document_family)
    family_match = pred_family == cand.family

    predicted_field_count = max(
        0, doc_summary.audited_field_count - doc_summary.missing_prediction_count
    )

    obs = Phase9FDocumentObservation(
        alias=cand.alias,
        cohort=cand.cohort,
        path=Phase9EvaluationPath.A_DETERMINISTIC,
        predicted_family=pred_family,
        family_match=family_match,
        confirmed_field_count=doc_summary.audited_field_count,
        predicted_field_count=predicted_field_count,
        exact_match_count=doc_summary.exact_match_count,
        normalized_match_count=doc_summary.normalized_match_count,
        false_positive_count=doc_summary.wrong_value_count,
        grounded_prediction_count=doc_summary.evidence_supported_count,
        grounded_correct_count=doc_summary.evidence_supported_count,
        unsupported_prediction_count=0,
        abstained_field_count=0,
        hallucination_count=0,
        completeness_score=pipeline_res.completeness.completeness_score
        if pipeline_res.completeness
        else 0.0,
        validation_pass=pipeline_res.validation_status == "accepted",
        review_required=pipeline_res.requires_review,
        runtime_seconds=runtime_seconds,
        peak_rss_mb=peak_rss_mb,
    )

    extra_meta = {
        "selected_parser": pipeline_res.selected_parser,
        "validation_status": pipeline_res.validation_status,
        "evidence_coverage": doc_summary.evidence_coverage,
        "missing_prediction_count": doc_summary.missing_prediction_count,
        "wrong_value_count": doc_summary.wrong_value_count,
        "evidence_supported_count": doc_summary.evidence_supported_count,
    }

    return obs, extra_meta
