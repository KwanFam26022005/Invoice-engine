"""End-to-end document processing pipeline and batch processor."""

from pathlib import Path
from typing import List, Optional
from pydantic import BaseModel

from document_engine.classification.classifier import DocumentClassifier
from document_engine.core.models import ProcessingSummary
from document_engine.extraction.mapper import DocumentMapper
from document_engine.intake.inspector import PDFInspector
from document_engine.ir.models import generate_run_id
from document_engine.routing.parser_router import ParserRouter
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

        # 1. Intake inspection
        source_doc, profile = self.inspector.inspect(pdf_path)

        # 2. Route & parse
        outcome = self.router.route_and_parse(
            source_doc, profile, enable_fallback=self.config.fallback_enabled
        )

        parse_res = outcome.selected_result
        if not parse_res.success or parse_res.document_ir is None:
            return PipelineResult(
                document_id=source_doc.document_id,
                pdf_profile=profile.pdf_profile.value,
                selected_parser=outcome.routing_decision.selected_parser,
                document_family="unknown",
                validation_status="failed",
                requires_review=True,
                database_path=str(self.paths.database_file),
            )

        doc_ir = parse_res.document_ir

        # 3. Classify
        classification = self.classifier.classify(doc_ir)

        # 4. Map to envelope
        envelope = self.mapper.map_to_envelope(doc_ir, classification)

        # 5. Validate
        validation_res = self.validator.validate(envelope)

        # 6. Store in DuckDB
        self.storage.store_document(envelope, validation_res, run_id=run_id)

        val_status = "accepted" if validation_res.is_valid and not validation_res.requires_review else "review_required"

        return PipelineResult(
            document_id=source_doc.document_id,
            pdf_profile=profile.pdf_profile.value,
            selected_parser=outcome.routing_decision.selected_parser,
            document_family=classification.document_family.value,
            validation_status=val_status,
            requires_review=validation_res.requires_review,
            database_path=str(self.paths.database_file),
            envelope=envelope,
            validation=validation_res,
        )

    def process_folder(
        self, folder_path: Path, run_id: Optional[str] = None
    ) -> tuple[ProcessingSummary, List[PipelineResult]]:
        folder_path = Path(folder_path).resolve()
        pdf_files = sorted(folder_path.glob("*.pdf"))

        summary = ProcessingSummary(received=len(pdf_files))
        results: List[PipelineResult] = []

        seen_sha256 = set()

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

            except Exception as e:
                summary.failed += 1

        return summary, results
