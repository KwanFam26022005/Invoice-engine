"""Docling native parser adapter for layout & table extraction on native PDFs via isolated worker."""

from pathlib import Path
from typing import List, Optional

from document_engine.core.models import PDFProfileType
from document_engine.ir.models import (
    BlockIR,
    DocumentIR,
    DocumentParseResult,
    DocumentProfile,
    PageIR,
    ParseWarning,
    ParserProvenance,
    SourceDocument,
    TableIR,
)
from document_engine.parsers.base import DocumentParser, ParserHealth, ParserSpec
from document_engine.runtime import WorkerClient, WorkerRequest


def dict_to_document_ir(doc_dict: dict, profile: DocumentProfile) -> DocumentIR:
    """Parse dictionary returned by worker back into strongly-typed DocumentIR."""
    pages: List[PageIR] = []
    for p_dict in doc_dict.get("pages", []):
        blocks: List[BlockIR] = []
        for b_dict in p_dict.get("blocks", []):
            blocks.append(BlockIR.model_validate(b_dict))

        tables: List[TableIR] = []
        for t_dict in p_dict.get("tables", []):
            tables.append(TableIR.model_validate(t_dict))

        pages.append(
            PageIR(
                page_id=p_dict["page_id"],
                page_number=p_dict["page_number"],
                width=p_dict.get("width"),
                height=p_dict.get("height"),
                blocks=blocks,
                tables=tables,
                text_content=p_dict.get("text_content", ""),
            )
        )

    prov_dict = doc_dict.get("provenance", {})
    provenance = ParserProvenance(
        parser_id=prov_dict.get("parser_id", "docling_native"),
        parser_version=prov_dict.get("parser_version", "2.0.0"),
        execution_time_seconds=prov_dict.get("execution_time_seconds", 0.0),
        config=prov_dict.get("config", {}),
    )

    warnings: List[ParseWarning] = [
        ParseWarning.model_validate(w) for w in doc_dict.get("warnings", [])
    ]

    doc_id = doc_dict.get("document_id", "doc_unknown")

    return DocumentIR(
        document_id=doc_id,
        source_document=SourceDocument.model_validate(doc_dict["source_document"]),
        profile=profile,
        provenance=provenance,
        pages=pages,
        full_text=doc_dict.get("full_text", ""),
        warnings=warnings,
    )


_DOCLING_NATIVE_DEFAULT_CONFIG: dict = {
    "do_ocr": False,
    "do_table_structure": True,
}


class DoclingNativeParser(DocumentParser):
    def __init__(
        self,
        config: Optional[dict] = None,
        worker_client: Optional[WorkerClient] = None,
    ):
        merged_config = {**_DOCLING_NATIVE_DEFAULT_CONFIG, **(config or {})}
        self._spec = ParserSpec(
            parser_id="docling_native",
            name="Docling Native Parser",
            version="2.0.0",
            supported_profiles=[PDFProfileType.NATIVE_PDF, PDFProfileType.MIXED_PDF],
            requires_gpu=False,
            is_fallback=False,
            config=merged_config,
        )
        self.worker_client = worker_client or WorkerClient()

    @property
    def spec(self) -> ParserSpec:
        return self._spec

    def healthcheck(self) -> ParserHealth:
        try:
            req = WorkerRequest(
                request_id="req_healthcheck_docling_native",
                parser_id=self.parser_id,
                operation="healthcheck",
            )
            resp = self.worker_client.execute_worker(req)
            if resp.success and resp.health_data:
                return ParserHealth(
                    parser_id=self.parser_id,
                    healthy=True,
                    message=f"Docling native worker ready ({resp.health_data.get('python_executable')})",
                    dependencies_available=True,
                )
            return ParserHealth(
                parser_id=self.parser_id,
                healthy=False,
                message=resp.error_message or "Docling native worker healthcheck failed",
                dependencies_available=bool(resp.health_data and resp.health_data.get("docling_installed")),
            )
        except Exception as e:
            return ParserHealth(
                parser_id=self.parser_id,
                healthy=False,
                message=f"Docling native worker unavailable: {e}",
                dependencies_available=False,
            )

    def supports(self, profile: DocumentProfile) -> bool:
        return profile.pdf_profile in (PDFProfileType.NATIVE_PDF, PDFProfileType.MIXED_PDF)

    def parse(self, document: SourceDocument, profile: DocumentProfile) -> DocumentParseResult:
        health = self.healthcheck()
        if not health.healthy:
            return DocumentParseResult(
                success=False,
                error_message=f"Docling Native unavailable: {health.message}",
            )

        pdf_path = Path(document.path)
        if not pdf_path.exists():
            return DocumentParseResult(
                success=False, error_message=f"File not found: {document.path}"
            )

        try:
            request = WorkerRequest(
                request_id=f"req_{document.document_id}_docling_native",
                parser_id=self.parser_id,
                input_path=str(pdf_path),
                document_id=document.document_id,
                source_sha256=document.sha256,
                page_count=document.page_count,
                options=self.spec.config,
            )

            resp = self.worker_client.execute_worker(request)

            if not resp.success or not resp.document_ir_dict:
                return DocumentParseResult(
                    success=False,
                    error_message=resp.error_message or "Docling Native worker failed",
                )

            doc_ir = dict_to_document_ir(resp.document_ir_dict, profile)
            return DocumentParseResult(success=True, document_ir=doc_ir)

        except Exception as e:
            return DocumentParseResult(
                success=False, error_message=f"Docling Native parse error: {e}"
            )
