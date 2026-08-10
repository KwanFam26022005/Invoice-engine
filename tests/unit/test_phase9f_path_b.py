"""Unit tests for the Phase 9F.2B controlled semantic dry-run adapter."""

from pathlib import Path

import fitz
import yaml

from document_engine.core.models import DocumentFamilyType
from document_engine.evaluation.phase9_contract import (
    EvaluationCohort,
    Phase9DocumentManifestEntry,
    Phase9Manifest,
)
from document_engine.evaluation.phase9f import Phase9EvaluationPath
from document_engine.evaluation.phase9f_path_b import (
    execute_phase9f_path_b_observation,
    probe_phase9f_path_b_alias,
)
from document_engine.semantic.contracts import (
    SemanticCandidate,
    SemanticExtractionResult,
)


BASELINE = "2eb4b3f7695ef6693369d732a8520fe243269d7a"


def _write_tax_pdf(path: Path) -> None:
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text(
        (72, 72),
        "Certificate of personal income tax withholding\n"
        "Certificate number: CERT-001\n"
        "PIT withholding amount: 1000",
    )
    doc.save(path)
    doc.close()


def _write_manifest(root: Path, *, manifest_family: DocumentFamilyType) -> Path:
    source_ref = "workspace/private/phase9/documents/current_tax_001.pdf"
    audit_ref = "workspace/private/phase9/audit/current_tax_001.audit.json"

    source_path = root / source_ref
    source_path.parent.mkdir(parents=True, exist_ok=True)
    _write_tax_pdf(source_path)

    audit_path = root / audit_ref
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    audit_path.write_text(
        """{
  "document_id": "synthetic-tax",
  "family": "tax_withholding_certificate",
  "fields": {
    "certificate_number": {"expected": "CERT-001", "status": "CONFIRMED"},
    "withheld_tax": {"expected": 1000, "status": "CONFIRMED"}
  }
}
""",
        encoding="utf-8",
    )

    manifest = Phase9Manifest(
        frozen_baseline_revision=BASELINE,
        documents=[
            Phase9DocumentManifestEntry(
                alias="current_tax_001",
                family=manifest_family,
                cohort=EvaluationCohort.CURRENT_PILOT,
                layout_group="synthetic-tax-layout",
                source_ref=source_ref,
                audit_ref=audit_ref,
            )
        ],
    )
    manifest_path = root / "workspace/private/phase9/phase9_manifest.yaml"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        yaml.safe_dump(manifest.model_dump(mode="json"), sort_keys=False),
        encoding="utf-8",
    )
    return manifest_path


class _FakeSemanticExtractor:
    extractor_id = "fake_semantic"

    def __init__(self):
        self.request = None

    def supports(self, family, target_schema_name, document_ir):
        return True

    def extract(self, request):
        self.request = request
        return SemanticExtractionResult(
            extractor_id=self.extractor_id,
            extractor_version="test",
            document_id=request.document_id,
            family=request.family,
            success=True,
            candidates=[
                SemanticCandidate(
                    field_path="certificate_number",
                    value="CERT-001",
                    raw_value="CERT-001",
                    source_method="fake_semantic",
                ),
                SemanticCandidate(
                    field_path="withheld_tax",
                    value=1000,
                    raw_value=1000,
                    source_method="fake_semantic",
                ),
            ],
        )


def test_path_b_probe_uses_runtime_classifier_not_manifest_family(tmp_path: Path):
    _write_manifest(tmp_path, manifest_family=DocumentFamilyType.SALES_INVOICE)

    report = probe_phase9f_path_b_alias(
        alias="current_tax_001",
        repo_root=tmp_path,
    )

    assert report.page_count == 1
    assert report.block_count > 0
    assert report.full_text_char_count > 0
    assert report.selected_parser == "pymupdf_native"
    assert report.predicted_family == DocumentFamilyType.TAX_WITHHOLDING_CERTIFICATE
    assert report.semantic_schema_supported is True
    assert report.eligible is True


def test_path_b_execution_never_uses_manifest_family_as_schema_oracle(tmp_path: Path):
    _write_manifest(tmp_path, manifest_family=DocumentFamilyType.SALES_INVOICE)
    extractor = _FakeSemanticExtractor()

    observation, metadata = execute_phase9f_path_b_observation(
        alias="current_tax_001",
        repo_root=tmp_path,
        extractor=extractor,
    )

    assert extractor.request is not None
    assert extractor.request.family == DocumentFamilyType.TAX_WITHHOLDING_CERTIFICATE
    assert extractor.request.target_schema_name == "TaxWithholdingCertificatePayload"
    assert extractor.request.policy.allow_network is False

    assert observation.path == Phase9EvaluationPath.B_DOCLING_SEMANTIC
    assert observation.predicted_family == DocumentFamilyType.TAX_WITHHOLDING_CERTIFICATE
    assert observation.family_match is False
    assert observation.confirmed_field_count == 2
    assert observation.predicted_field_count == 2
    assert observation.normalized_match_count == 2
    assert observation.grounded_prediction_count == 2
    assert observation.grounded_correct_count == 2
    assert observation.unsupported_prediction_count == 0

    assert metadata["schema_condition_source"] == "frozen_classifier_output"
    assert metadata["oracle_family_used_for_execution"] is False
    assert metadata["audit_loaded_after_inference"] is True
    assert metadata["private_values_returned"] is False
    assert metadata["semantic_timeout_seconds"] is None


def test_path_b_real_extractor_requires_manual_terminal_gate(tmp_path: Path):
    _write_manifest(tmp_path, manifest_family=DocumentFamilyType.TAX_WITHHOLDING_CERTIFICATE)

    try:
        execute_phase9f_path_b_observation(
            alias="current_tax_001",
            repo_root=tmp_path,
        )
    except RuntimeError as exc:
        assert str(exc) == "MANUAL_TERMINAL_TASK_REQUIRED"
    else:
        raise AssertionError("Real Path B execution must require the manual terminal gate.")


def test_path_b_real_extractor_receives_configured_timeout(tmp_path: Path, monkeypatch):
    _write_manifest(tmp_path, manifest_family=DocumentFamilyType.TAX_WITHHOLDING_CERTIFICATE)
    captured = {}

    class _ConfiguredFakeExtractor(_FakeSemanticExtractor):
        def __init__(self, timeout: float):
            super().__init__()
            captured["timeout"] = timeout

    monkeypatch.setattr(
        "document_engine.semantic.extractors.docling_semantic.DoclingSemanticExtractor",
        _ConfiguredFakeExtractor,
    )

    _observation, metadata = execute_phase9f_path_b_observation(
        alias="current_tax_001",
        repo_root=tmp_path,
        allow_heavy_execution=True,
        semantic_timeout_seconds=600.0,
    )

    assert captured["timeout"] == 600.0
    assert metadata["semantic_timeout_seconds"] == 600.0


def test_path_b_rejects_non_positive_timeout(tmp_path: Path):
    _write_manifest(tmp_path, manifest_family=DocumentFamilyType.TAX_WITHHOLDING_CERTIFICATE)

    try:
        execute_phase9f_path_b_observation(
            alias="current_tax_001",
            repo_root=tmp_path,
            extractor=_FakeSemanticExtractor(),
            semantic_timeout_seconds=0,
        )
    except ValueError as exc:
        assert "greater than zero" in str(exc)
    else:
        raise AssertionError("Path B must reject a non-positive semantic timeout.")
