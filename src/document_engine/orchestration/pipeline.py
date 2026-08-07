"""End-to-end document processing pipeline with two-level execution and semantic fallback."""

from pathlib import Path
from typing import List, Optional
from pydantic import BaseModel

from document_engine.classification.classifier import DocumentClassifier
from document_engine.core.models import ProcessingSummary
from document_engine.extraction.candidate import FamilyCompletenessReport
from document_engine.extraction.mapper import DocumentMapper
from document_engine.intake.inspector import PDFInspector
from document_engine.ir.models import generate_run_id
from document_engine.routing.parser_router import ParserRouter, RoutingDecision
from document_engine.schemas.family_schemas import BusinessDocumentEnvelope
from document_engine.settings import AppConfig, get_workspace_paths
from document_engine.storage.database import DuckDBStorage
from document_engine.validation.validator import BusinessValidator, ValidationResult


class PipelineResult(BaseModel):
    document_id: str
    pdf_profile: str
    selected_parser: str
    document_family: str
    validation_status: str
    requires_review: bool
    database_path: str
    envelope: Optional[BusinessDocumentEnvelope] = None
    validation: Optional[ValidationResult] = None
    completeness: Optional[FamilyCompletenessReport] = None
    routing_decision: Optional[RoutingDecision] = None


class DocumentPipeline:
    def __init__(self, config: Optional[AppConfig] = None):
        self.config = config or AppConfig.load_from_file()
        self.paths = get_workspace_paths(Path(self.config.workspace_root))
        self.paths.ensure_directories()

        self.inspector = PDFInspector()
        self.router = ParserRouter(policy=self.config.default_parser_policy)
        self.classifier = DocumentClassifier()
        self.mapper = DocumentMapper()
        self.validator = BusinessValidator(tolerance=self.config.validation_tolerance)
        self.storage = DuckDBStorage(self.paths.database_file)

    def process_file(self, pdf_path: Path, run_id: Optional[str] = None) -> PipelineResult:
        pdf_path = Path(pdf_path).resolve()
        if run_id is None:
            run_id = generate_run_id()

        # Level 1: Intake inspection & Document Parsing
        source_doc, profile = self.inspector.inspect(pdf_path)

        outcome = self.router.route_and_parse(
            source_doc, profile, enable_fallback=self.config.fallback_enabled
        )

        parse_res = outcome.selected_result
        if not parse_res.success or parse_res.document_ir is None:
            return PipelineResult(
                document_id=source_doc.document_id,
                pdf_profile=profile.pdf_profile.value,
                selected_parser=outcome.routing_decision.actual_parser,
                document_family="unknown",
                validation_status="failed",
                requires_review=True,
                database_path=str(self.paths.database_file),
                routing_decision=outcome.routing_decision,
            )

        doc_ir = parse_res.document_ir

        # Level 2: Business Interpretation
        classification = self.classifier.classify(doc_ir)
        envelope = self.mapper.map_to_envelope(doc_ir, classification)
        validation_res = self.validator.validate(envelope)
        completeness = self.mapper.evaluate_completeness(envelope, doc_ir)

        # Semantic Fallback Loop: check if completeness or critical missing fields trigger semantic fallback
        if (
            completeness.requires_review
            and outcome.fallback_result is not None
            and outcome.fallback_result.success
            and outcome.fallback_result.document_ir
        ):
            # Try interpreting fallback DocumentIR
            fb_ir = outcome.fallback_result.document_ir
            fb_class = self.classifier.classify(fb_ir)
            fb_env = self.mapper.map_to_envelope(fb_ir, fb_class)
            fb_val = self.validator.validate(fb_env)
            fb_comp = self.mapper.evaluate_completeness(fb_env, fb_ir)

            if fb_comp.completeness_score > completeness.completeness_score:
                doc_ir = fb_ir
                classification = fb_class
                envelope = fb_env
                validation_res = fb_val
                completeness = fb_comp
                outcome.routing_decision.selection_reason = (
                    "Selected fallback parser result due to higher semantic completeness score "
                    f"({fb_comp.completeness_score:.2f} vs {completeness.completeness_score:.2f})."
                )

        # Store in DuckDB Storage V2
        self.storage.store_document(
            envelope=envelope,
            validation=validation_res,
            routing_decision=outcome.routing_decision,
            completeness=completeness,
            run_id=run_id,
        )

        requires_review = (
            validation_res.requires_review or completeness.requires_review
        )
        val_status = "accepted" if validation_res.is_valid and not requires_review else "review_required"

        return PipelineResult(
            document_id=source_doc.document_id,
            pdf_profile=profile.pdf_profile.value,
            selected_parser=outcome.routing_decision.actual_parser,
            document_family=classification.document_family.value,
            validation_status=val_status,
            requires_review=requires_review,
            database_path=str(self.paths.database_file),
            envelope=envelope,
            validation=validation_res,
            completeness=completeness,
            routing_decision=outcome.routing_decision,
        )

    def process_folder(
        self, folder_path: Path, run_id: Optional[str] = None
    ) -> tuple[ProcessingSummary, List[PipelineResult]]:
        folder_path = Path(folder_path).resolve()
        pdf_files = sorted(folder_path.glob("*.pdf"))

        summary = ProcessingSummary(received=len(pdf_files))
        results: List[PipelineResult] = []

        for pdf_file in pdf_files:
            try:
                res = self.process_file(pdf_file, run_id=run_id)
                results.append(res)
                summary.processed += 1

                if res.validation_status == "accepted":
                    summary.accepted += 1
                elif res.requires_review:
                    summary.review_required += 1

                if res.document_family == "unknown":
                    summary.unknown += 1

            except Exception:
                summary.failed += 1

        return summary, results
