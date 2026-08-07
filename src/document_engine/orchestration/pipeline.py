"""End-to-end document processing pipeline with two-level execution, semantic fallback, and parser disagreement policy."""

from decimal import Decimal
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

    def _check_parser_disagreement(
        self, primary_env: BusinessDocumentEnvelope, fallback_env: BusinessDocumentEnvelope
    ) -> bool:
        """Check if primary and fallback envelopes conflict on critical fields."""
        p_c = getattr(primary_env.payload, "common", None)
        f_c = getattr(fallback_env.payload, "common", None)

        if p_c and f_c:
            if p_c.document_number and f_c.document_number and p_c.document_number != f_c.document_number:
                return True
            if p_c.issue_date and f_c.issue_date and p_c.issue_date != f_c.issue_date:
                return True
            if p_c.grand_total is not None and f_c.grand_total is not None and abs(p_c.grand_total - f_c.grand_total) > Decimal("0.01"):
                return True

            p_seller = p_c.seller.tax_id if p_c.seller else None
            f_seller = f_c.seller.tax_id if f_c.seller else None
            if p_seller and f_seller and p_seller != f_seller:
                return True

        # Check Tax Certificate withheld_tax if applicable
        p_tax = getattr(primary_env.payload, "withheld_tax", None)
        f_tax = getattr(fallback_env.payload, "withheld_tax", None)
        return bool(p_tax is not None and f_tax is not None and abs(p_tax - f_tax) > Decimal("0.01"))

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

        # Level 2: Business Interpretation (Primary)
        classification = self.classifier.classify(doc_ir)
        envelope = self.mapper.map_to_envelope(doc_ir, classification)
        validation_res = self.validator.validate(envelope)
        completeness = self.mapper.evaluate_completeness(envelope, doc_ir)

        parser_disagreement = False

        # Semantic Fallback Loop
        if (
            completeness.requires_review
            and outcome.fallback_result is not None
            and outcome.fallback_result.success
            and outcome.fallback_result.document_ir
        ):
            fb_ir = outcome.fallback_result.document_ir
            fb_class = self.classifier.classify(fb_ir)
            fb_env = self.mapper.map_to_envelope(fb_ir, fb_class)
            fb_val = self.validator.validate(fb_env)
            fb_comp = self.mapper.evaluate_completeness(fb_env, fb_ir)

            # Preserve scores before selection
            primary_score = completeness.completeness_score
            fallback_score = fb_comp.completeness_score

            # Store signals
            outcome.routing_decision.profile_signals["primary_family"] = classification.document_family.value
            outcome.routing_decision.profile_signals["fallback_family"] = fb_class.document_family.value
            outcome.routing_decision.profile_signals["primary_completeness_score"] = primary_score
            outcome.routing_decision.profile_signals["fallback_completeness_score"] = fallback_score

            # Check parser disagreement
            parser_disagreement = self._check_parser_disagreement(envelope, fb_env)
            if parser_disagreement:
                outcome.routing_decision.profile_signals["parser_disagreement"] = True

            if fallback_score > primary_score:
                doc_ir = fb_ir
                classification = fb_class
                envelope = fb_env
                validation_res = fb_val
                completeness = fb_comp
                outcome.routing_decision.selection_reason = (
                    "Selected fallback parser result due to higher semantic completeness score "
                    f"({fallback_score:.2f} vs {primary_score:.2f})."
                )

        # Store in DuckDB Storage
        self.storage.store_document(
            envelope=envelope,
            validation=validation_res,
            routing_decision=outcome.routing_decision,
            routing_outcome=outcome,
            completeness=completeness,
            source_doc=source_doc,
            run_id=run_id,
        )

        requires_review = (
            validation_res.requires_review
            or completeness.requires_review
            or parser_disagreement
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

        if run_id is None:
            run_id = generate_run_id()

        self.storage.start_processing_run(run_id, total_documents=len(pdf_files))

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

            # Update batch run progress in storage
            self.storage.update_processing_run(
                run_id=run_id,
                processed_count=summary.processed,
                accepted_count=summary.accepted,
                review_required_count=summary.review_required,
                failed_count=summary.failed,
                status="running" if summary.processed < summary.received else "completed",
            )

        return summary, results
