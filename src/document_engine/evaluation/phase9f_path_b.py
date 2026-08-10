"""Phase 9F.2B controlled Docling semantic dry-run adapter.

This module keeps the Path B execution boundary explicit:
- only CURRENT_PILOT aliases are accepted by the dry-run adapter;
- frozen pre-semantic preprocessing uses PyMuPDF native extraction;
- semantic schema selection comes only from the frozen runtime classifier output;
- manifest/audit family labels are never supplied to semantic extraction;
- audit values are loaded only after semantic inference and deterministic grounding;
- real heavyweight inference requires an explicit manual-terminal gate.

The returned observation and metadata are privacy-safe count/structure only. No
source text, extracted value, filename, absolute path, or audit value is returned.
"""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import time
from typing import Any, Dict, Optional

from pydantic import BaseModel

from document_engine.classification.classifier import ClassificationResult, DocumentClassifier
from document_engine.core.models import DocumentFamilyType
from document_engine.evaluation.audit_models import DocumentAuditSpec, FieldAuditStatus
from document_engine.evaluation.comparator import compare_values
from document_engine.evaluation.phase9_contract import EvaluationCohort, Phase9Manifest
from document_engine.evaluation.phase9f import (
    Phase9EvaluationPath,
    Phase9FDocumentObservation,
)
from document_engine.intake.inspector import PDFInspector
from document_engine.ir.models import DocumentIR
from document_engine.parsers.pymupdf_native import PyMuPDFNativeParser
from document_engine.semantic.contracts import (
    SemanticCandidateStatus,
    SemanticExtractionPolicy,
    SemanticExtractionRequest,
    SemanticExtractionResult,
    SemanticExtractor,
)
from document_engine.semantic.grounding import EvidenceGrounder, GroundingStatus
from document_engine.semantic.schema_registry import (
    get_semantic_schema,
    supports_semantic_schema,
)


_PATH_B_SUPPORTED_FAMILIES = {
    DocumentFamilyType.SALES_INVOICE,
    DocumentFamilyType.UTILITY_CONSUMPTION_INVOICE,
    DocumentFamilyType.TAX_WITHHOLDING_CERTIFICATE,
}


class Phase9FPathBEligibility(BaseModel):
    """Privacy-safe structure-only eligibility record for Path B."""

    alias: str
    page_count: int
    block_count: int
    table_count: int
    full_text_char_count: int
    selected_parser: str
    predicted_family: DocumentFamilyType
    classifier_confidence: float
    semantic_schema_supported: bool
    eligible: bool


@dataclass
class _PreparedPathB:
    """Private in-memory preparation state. Never serialize this dataclass."""

    manifest_entry: Any
    document_ir: DocumentIR
    classification: ClassificationResult
    eligibility: Phase9FPathBEligibility


def _load_manifest_entry(
    alias: str,
    repo_root: Path,
    manifest_path: str,
):
    root = Path(repo_root).resolve()
    manifest_file = (root / manifest_path).resolve()
    if manifest_file != root and root not in manifest_file.parents:
        raise ValueError("Phase 9F manifest reference escaped repository root.")
    if not manifest_file.is_file():
        raise FileNotFoundError("Private Phase 9 manifest is not available.")

    manifest = Phase9Manifest.load_yaml(manifest_file)
    entry = next((item for item in manifest.documents if item.alias == alias), None)
    if entry is None:
        raise ValueError(f"Phase 9 alias '{alias}' is not registered.")
    return root, entry


def _resolve_private_ref(root: Path, relative_ref: str, alias: str, label: str) -> Path:
    resolved = (root / relative_ref).resolve()
    if resolved != root and root not in resolved.parents:
        raise ValueError("Private Phase 9 reference escaped repository root.")
    if not resolved.is_file():
        raise FileNotFoundError(f"Private {label} is missing for alias '{alias}'.")
    return resolved


def _prepare_path_b(
    alias: str,
    repo_root: Path,
    manifest_path: str,
) -> _PreparedPathB:
    root, entry = _load_manifest_entry(alias, repo_root, manifest_path)

    if entry.cohort != EvaluationCohort.CURRENT_PILOT:
        raise ValueError("Phase 9F.2B dry run is restricted to CURRENT_PILOT aliases.")

    source_pdf = _resolve_private_ref(root, entry.source_ref, alias, "source PDF")

    inspector = PDFInspector()
    source_doc, profile = inspector.inspect(source_pdf)

    # Frozen pre-semantic preprocessing for the Path B dry run. No OCR/VLM fallback.
    parser = PyMuPDFNativeParser()
    parse_result = parser.parse(source_doc, profile)
    if not parse_result.success or parse_result.document_ir is None:
        raise RuntimeError(f"Frozen pre-semantic preprocessing failed for alias '{alias}'.")

    document_ir = parse_result.document_ir
    classification = DocumentClassifier().classify(document_ir)
    predicted_family = classification.document_family

    page_count = len(document_ir.pages)
    block_count = sum(len(page.blocks) for page in document_ir.pages)
    table_count = sum(len(page.tables) for page in document_ir.pages)
    full_text_char_count = len(document_ir.full_text)
    schema_supported = supports_semantic_schema(predicted_family)
    eligible = (
        full_text_char_count > 0
        and block_count > 0
        and predicted_family in _PATH_B_SUPPORTED_FAMILIES
        and schema_supported
    )

    eligibility = Phase9FPathBEligibility(
        alias=alias,
        page_count=page_count,
        block_count=block_count,
        table_count=table_count,
        full_text_char_count=full_text_char_count,
        selected_parser=document_ir.provenance.parser_id,
        predicted_family=predicted_family,
        classifier_confidence=classification.confidence,
        semantic_schema_supported=schema_supported,
        eligible=eligible,
    )

    return _PreparedPathB(
        manifest_entry=entry,
        document_ir=document_ir,
        classification=classification,
        eligibility=eligibility,
    )


def probe_phase9f_path_b_alias(
    alias: str,
    repo_root: Path = Path("."),
    manifest_path: str = "workspace/private/phase9/phase9_manifest.yaml",
) -> Phase9FPathBEligibility:
    """Run only frozen pre-semantic preprocessing and return privacy-safe eligibility."""

    prepared = _prepare_path_b(alias, repo_root, manifest_path)
    return prepared.eligibility


def _load_audit_after_inference(
    prepared: _PreparedPathB,
    repo_root: Path,
) -> DocumentAuditSpec:
    root = Path(repo_root).resolve()
    audit_path = _resolve_private_ref(
        root,
        prepared.manifest_entry.audit_ref,
        prepared.manifest_entry.alias,
        "audit JSON",
    )
    return DocumentAuditSpec.model_validate_json(audit_path.read_text(encoding="utf-8"))


def _current_rss_mb() -> Optional[float]:
    try:
        import psutil

        return psutil.Process(os.getpid()).memory_info().rss / (1024 * 1024)
    except Exception:
        return None


def execute_phase9f_path_b_observation(
    alias: str,
    repo_root: Path = Path("."),
    manifest_path: str = "workspace/private/phase9/phase9_manifest.yaml",
    *,
    extractor: Optional[SemanticExtractor] = None,
    grounder: Optional[EvidenceGrounder] = None,
    allow_heavy_execution: bool = False,
) -> tuple[Phase9FDocumentObservation, Dict[str, Any]]:
    """Execute one controlled Path B observation.

    When ``extractor`` is omitted, real Docling/NuExtract inference is blocked unless
    ``allow_heavy_execution=True`` is supplied by an explicit manual-terminal runner.
    Injected extractors are intended for unit tests and do not trigger the heavy gate.
    """

    prepared = _prepare_path_b(alias, repo_root, manifest_path)
    eligibility = prepared.eligibility
    if not eligibility.eligible:
        raise ValueError(f"Alias '{alias}' is not PATH_B_DRY_RUN_ELIGIBLE.")

    # Critical fairness boundary: schema selection uses runtime classifier output only.
    predicted_family = prepared.classification.document_family
    schema_spec = get_semantic_schema(predicted_family)

    if extractor is None:
        if not allow_heavy_execution:
            raise RuntimeError("MANUAL_TERMINAL_TASK_REQUIRED")
        from document_engine.semantic.extractors.docling_semantic import DoclingSemanticExtractor

        extractor = DoclingSemanticExtractor()

    request = SemanticExtractionRequest(
        document_id=prepared.document_ir.document_id,
        family=predicted_family,
        target_schema_name=schema_spec.schema_name,
        document_ir=prepared.document_ir,
        policy=SemanticExtractionPolicy(
            local_runtime_only=True,
            allow_network=False,
            abstain_on_uncertain=True,
            max_candidates_per_field=1,
        ),
    )

    start = time.perf_counter()
    peak_rss_mb = _current_rss_mb()
    semantic_result = extractor.extract(request)
    runtime_seconds = time.perf_counter() - start
    end_rss = _current_rss_mb()
    if peak_rss_mb is None:
        peak_rss_mb = end_rss
    elif end_rss is not None:
        peak_rss_mb = max(peak_rss_mb, end_rss)

    if not isinstance(semantic_result, SemanticExtractionResult):
        semantic_result = SemanticExtractionResult.model_validate(semantic_result)
    if semantic_result.document_id != prepared.document_ir.document_id:
        raise ValueError("Path B semantic result document identity mismatch.")
    if semantic_result.family != predicted_family:
        raise ValueError("Path B semantic result family identity mismatch.")

    grounding_report = (grounder or EvidenceGrounder()).ground_result(
        semantic_result,
        prepared.document_ir,
    )

    # Audit is intentionally loaded only after semantic inference and grounding.
    audit_spec = _load_audit_after_inference(prepared, repo_root)
    confirmed = {
        path: entry
        for path, entry in audit_spec.fields.items()
        if entry.status == FieldAuditStatus.CONFIRMED
    }

    proposed = [
        candidate
        for candidate in semantic_result.candidates
        if candidate.status == SemanticCandidateStatus.PROPOSED
    ]

    exact_match_count = 0
    normalized_match_count = 0
    false_positive_count = 0
    normalized_by_candidate_id: Dict[int, bool] = {}

    for candidate in proposed:
        audit_entry = confirmed.get(candidate.field_path)
        if audit_entry is None:
            false_positive_count += 1
            normalized_by_candidate_id[id(candidate)] = False
            continue
        exact, normalized = compare_values(
            audit_entry.expected,
            candidate.value,
            candidate.field_path,
        )
        exact_match_count += int(exact)
        normalized_match_count += int(normalized)
        normalized_by_candidate_id[id(candidate)] = normalized
        if not normalized:
            false_positive_count += 1

    grounded_prediction_count = 0
    grounded_correct_count = 0
    unsupported_prediction_count = 0
    for grounded in grounding_report.candidates:
        if grounded.grounding_status == GroundingStatus.GROUNDED:
            grounded_prediction_count += 1
            if normalized_by_candidate_id.get(id(grounded.candidate), False):
                grounded_correct_count += 1
        elif grounded.grounding_status == GroundingStatus.UNSUPPORTED:
            unsupported_prediction_count += 1

    confirmed_abstentions = {
        field_path
        for field_path in semantic_result.abstained_fields
        if field_path in confirmed
    }

    # Manifest family is used only now, after execution, for evaluation bookkeeping.
    family_match = predicted_family == prepared.manifest_entry.family

    observation = Phase9FDocumentObservation(
        alias=alias,
        cohort=prepared.manifest_entry.cohort,
        path=Phase9EvaluationPath.B_DOCLING_SEMANTIC,
        predicted_family=predicted_family,
        family_match=family_match,
        confirmed_field_count=len(confirmed),
        predicted_field_count=len(proposed),
        exact_match_count=exact_match_count,
        normalized_match_count=normalized_match_count,
        false_positive_count=false_positive_count,
        grounded_prediction_count=grounded_prediction_count,
        grounded_correct_count=grounded_correct_count,
        unsupported_prediction_count=unsupported_prediction_count,
        abstained_field_count=len(confirmed_abstentions),
        # Operational dry-run proxy: proposed values that cannot be grounded are
        # counted as hallucinations. This definition is explicit and deterministic.
        hallucination_count=unsupported_prediction_count,
        completeness_score=None,
        validation_pass=None,
        review_required=None,
        runtime_seconds=runtime_seconds,
        peak_rss_mb=peak_rss_mb,
    )

    metadata: Dict[str, Any] = {
        "selected_parser": eligibility.selected_parser,
        "page_count": eligibility.page_count,
        "block_count": eligibility.block_count,
        "table_count": eligibility.table_count,
        "full_text_char_count": eligibility.full_text_char_count,
        "predicted_family": predicted_family.value,
        "classifier_confidence": eligibility.classifier_confidence,
        "semantic_schema_name": schema_spec.schema_name,
        "semantic_schema_supported": eligibility.semantic_schema_supported,
        "extractor_id": semantic_result.extractor_id,
        "extractor_version": semantic_result.extractor_version,
        "semantic_success": semantic_result.success,
        "semantic_error_code": semantic_result.error_code,
        "candidate_count": len(proposed),
        "grounded_count": grounding_report.grounded_count,
        "unsupported_count": grounding_report.unsupported_count,
        "abstained_count": len(semantic_result.abstained_fields),
        "audit_loaded_after_inference": True,
        "schema_condition_source": "frozen_classifier_output",
        "oracle_family_used_for_execution": False,
        "network_allowed": False,
        "private_values_returned": False,
    }

    return observation, metadata
