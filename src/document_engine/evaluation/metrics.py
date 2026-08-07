"""Evaluation metrics calculator using audited denominator rules and failure taxonomy."""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from document_engine.core.field_paths import get_field_value
from document_engine.evaluation.audit_models import DocumentAuditSpec, FieldAuditStatus
from document_engine.evaluation.comparator import compare_values
from document_engine.evaluation.failure_taxonomy import FailureCategory
from document_engine.orchestration.pipeline import PipelineResult


class FieldEvaluationResult(BaseModel):
    field_path: str
    audit_status: str
    expected_value: Optional[Any] = None
    actual_value: Optional[Any] = None
    exact_match: bool = False
    normalized_match: bool = False
    has_evidence: bool = False
    failure_category: Optional[FailureCategory] = None


class DocumentEvaluationSummary(BaseModel):
    document_id: str
    family: str
    pdf_profile: str
    selected_parser: str
    validation_status: str
    audited_field_count: int = 0
    exact_match_count: int = 0
    normalized_match_count: int = 0
    missing_prediction_count: int = 0
    wrong_value_count: int = 0
    evidence_supported_count: int = 0
    evidence_coverage: float = 0.0
    field_results: List[FieldEvaluationResult] = Field(default_factory=list)
    failure_categories: List[FailureCategory] = Field(default_factory=list)


class AggregateEvaluationReport(BaseModel):
    audited_documents: int = 0
    total_audited_fields: int = 0  # Strictly CONFIRMED fields denominator
    exact_match_count: int = 0
    normalized_match_count: int = 0
    missing_prediction_count: int = 0
    wrong_value_count: int = 0
    total_evidence_supported_fields: int = 0
    exact_match_rate: float = 0.0
    normalized_match_rate: float = 0.0
    overall_evidence_coverage: float = 0.0
    family_summaries: Dict[str, Dict[str, Any]] = Field(default_factory=dict)
    failure_category_counts: Dict[str, int] = Field(default_factory=dict)


class Evaluator:
    """Evaluates pipeline output against private ground-truth audit specifications."""

    def evaluate_document(
        self,
        pipeline_result: PipelineResult,
        audit_spec: Optional[DocumentAuditSpec] = None,
    ) -> DocumentEvaluationSummary:
        doc_id = pipeline_result.document_id
        family = pipeline_result.document_family
        profile = pipeline_result.pdf_profile
        parser_id = pipeline_result.selected_parser

        summary = DocumentEvaluationSummary(
            document_id=doc_id,
            family=family,
            pdf_profile=profile,
            selected_parser=parser_id,
            validation_status=pipeline_result.validation_status,
        )

        failures: List[FailureCategory] = []

        if pipeline_result.validation_status == "review_required":
            failures.append(FailureCategory.HUMAN_REVIEW_REQUIRED)

        if pipeline_result.routing_decision and pipeline_result.routing_decision.fallback_trigger:
            failures.append(FailureCategory.SEMANTIC_FALLBACK_USED)

        if pipeline_result.routing_decision and pipeline_result.routing_decision.profile_signals.get("parser_disagreement"):
            failures.append(FailureCategory.PARSER_DISAGREEMENT)

        if not audit_spec or not audit_spec.fields:
            summary.failure_categories = sorted(set(failures), key=lambda x: x.value)
            return summary

        audited_count = 0
        exact_cnt = 0
        norm_cnt = 0
        missing_cnt = 0
        wrong_cnt = 0
        evidence_supported_cnt = 0

        envelope = pipeline_result.envelope

        for f_path, audit_entry in audit_spec.fields.items():
            # STRICT REQUIREMENT 1: Only CONFIRMED audit status is included in audited denominator
            if audit_entry.status != FieldAuditStatus.CONFIRMED:
                continue

            audited_count += 1
            expected = audit_entry.expected

            actual = None
            has_ev = False
            if envelope and envelope.payload:
                try:
                    actual = get_field_value(envelope.payload, f_path)
                except Exception:
                    actual = None

            if envelope and envelope.field_candidates and f_path in envelope.field_candidates:
                cand = envelope.field_candidates[f_path]
                if cand.evidence_references and len(cand.evidence_references) > 0:
                    has_ev = True

            if has_ev:
                evidence_supported_cnt += 1

            exact_m, norm_m = compare_values(expected, actual, f_path)

            # STRICT REQUIREMENT 2: Independent Exact and Normalized Match counting
            if exact_m:
                exact_cnt += 1

            field_fail: Optional[FailureCategory] = None
            if norm_m:
                norm_cnt += 1
            else:
                if actual is None and expected is not None:
                    missing_cnt += 1
                    field_fail = FailureCategory.FIELD_NOT_EXTRACTED
                else:
                    wrong_cnt += 1
                    field_fail = FailureCategory.FIELD_WRONG_VALUE
                failures.append(field_fail)

            summary.field_results.append(
                FieldEvaluationResult(
                    field_path=f_path,
                    audit_status=audit_entry.status.value,
                    expected_value=expected,
                    actual_value=actual,
                    exact_match=exact_m,
                    normalized_match=norm_m,
                    has_evidence=has_ev,
                    failure_category=field_fail,
                )
            )

        summary.audited_field_count = audited_count
        summary.exact_match_count = exact_cnt
        summary.normalized_match_count = norm_cnt
        summary.missing_prediction_count = missing_cnt
        summary.wrong_value_count = wrong_cnt
        summary.evidence_supported_count = evidence_supported_cnt
        summary.evidence_coverage = (
            evidence_supported_cnt / audited_count if audited_count > 0 else 0.0
        )
        summary.failure_categories = sorted(set(failures), key=lambda x: x.value)

        return summary

    def aggregate_summaries(
        self, summaries: List[DocumentEvaluationSummary]
    ) -> AggregateEvaluationReport:
        report = AggregateEvaluationReport()
        report.audited_documents = sum(
            1 for summary in summaries if summary.audited_field_count > 0
        )

        cat_counts: Dict[str, int] = {}
        family_stats: Dict[str, Dict[str, Any]] = {}

        for s in summaries:
            report.total_audited_fields += s.audited_field_count
            report.exact_match_count += s.exact_match_count
            report.normalized_match_count += s.normalized_match_count
            report.missing_prediction_count += s.missing_prediction_count
            report.wrong_value_count += s.wrong_value_count
            report.total_evidence_supported_fields += s.evidence_supported_count

            # Tally categories
            for cat in s.failure_categories:
                cat_counts[cat.value] = cat_counts.get(cat.value, 0) + 1

            # Tally per family
            fam = s.family
            if fam not in family_stats:
                family_stats[fam] = {
                    "doc_count": 0,
                    "audited_fields": 0,
                    "exact_matches": 0,
                    "normalized_matches": 0,
                    "evidence_supported": 0,
                }
            family_stats[fam]["doc_count"] += 1
            family_stats[fam]["audited_fields"] += s.audited_field_count
            family_stats[fam]["exact_matches"] += s.exact_match_count
            family_stats[fam]["normalized_matches"] += s.normalized_match_count
            family_stats[fam]["evidence_supported"] += s.evidence_supported_count

        if report.total_audited_fields > 0:
            report.exact_match_rate = report.exact_match_count / report.total_audited_fields
            report.normalized_match_rate = report.normalized_match_count / report.total_audited_fields
            # STRICT REQUIREMENT 3: Aggregate overall evidence coverage
            report.overall_evidence_coverage = report.total_evidence_supported_fields / report.total_audited_fields

        report.failure_category_counts = cat_counts
        report.family_summaries = family_stats
        return report
