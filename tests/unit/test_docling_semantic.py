"""Synthetic tests for the Docling semantic extraction canary contracts."""

from document_engine.core.models import DocumentFamilyType, PDFProfileType
from document_engine.ir.models import (
    DocumentIR,
    DocumentProfile,
    PageIR,
    ParserProvenance,
    SourceDocument,
)
from document_engine.runtime.worker_client import resolve_worker_script
from document_engine.runtime.worker_contracts import WorkerResponse
from document_engine.semantic import (
    SemanticExtractionPolicy,
    SemanticExtractionRequest,
    flatten_semantic_data,
    get_semantic_schema,
    supports_semantic_schema,
)
from document_engine.semantic.extractors import DoclingSemanticExtractor


class FakeWorkerClient:
    def __init__(self, response: WorkerResponse):
        self.response = response
        self.requests = []

    def execute_worker(self, request, timeout=None):
        self.requests.append((request, timeout))
        return self.response


def _document() -> DocumentIR:
    source = SourceDocument(
        document_id="doc_semantic",
        filename="synthetic.pdf",
        path="workspace/synthetic.pdf",
        sha256="synthetic-sha",
        page_count=1,
    )
    return DocumentIR(
        document_id="doc_semantic",
        source_document=source,
        profile=DocumentProfile(
            pdf_profile=PDFProfileType.NATIVE_PDF,
            has_text_layer=True,
        ),
        provenance=ParserProvenance(parser_id="pymupdf_native", parser_version="test"),
        pages=[PageIR(page_id="doc_semantic_p0001", page_number=1)],
    )


def _request(max_candidates_per_field: int = 1) -> SemanticExtractionRequest:
    return SemanticExtractionRequest(
        document_id="doc_semantic",
        family=DocumentFamilyType.SALES_INVOICE,
        target_schema_name="SalesInvoicePayload",
        document_ir=_document(),
        policy=SemanticExtractionPolicy(max_candidates_per_field=max_candidates_per_field),
    )


def test_schema_registry_supports_only_initial_phase9d_families():
    assert supports_semantic_schema(
        DocumentFamilyType.SALES_INVOICE, "SalesInvoicePayload"
    )
    assert supports_semantic_schema(
        DocumentFamilyType.UTILITY_CONSUMPTION_INVOICE,
        "UtilityConsumptionInvoicePayload",
    )
    assert supports_semantic_schema(
        DocumentFamilyType.TAX_WITHHOLDING_CERTIFICATE,
        "TaxWithholdingCertificatePayload",
    )
    assert not supports_semantic_schema(DocumentFamilyType.UNKNOWN, "UnknownBusinessDocumentPayload")

    sales = get_semantic_schema(DocumentFamilyType.SALES_INVOICE)
    assert sales.template["common"]["grand_total"] == "float"
    assert sales.template["line_items"][0]["quantity"] == "float"


def test_schema_registry_returns_deep_copy():
    first = get_semantic_schema(DocumentFamilyType.SALES_INVOICE)
    first.template["common"]["document_number"] = "changed"
    second = get_semantic_schema(DocumentFamilyType.SALES_INVOICE)
    assert second.template["common"]["document_number"] == "string"


def test_flatten_semantic_data_produces_atomic_paths_and_abstentions():
    values, abstained = flatten_semantic_data(
        {
            "common": {"document_number": "INV-X", "grand_total": None},
            "line_items": [
                {"description": "Service A", "quantity": 2, "amount": 100},
                {"description": "Service B", "quantity": None, "amount": 50},
            ],
        }
    )
    assert ("common.document_number", "INV-X") in values
    assert ("line_items[0].quantity", 2) in values
    assert ("line_items[1].amount", 50) in values
    assert "common.grand_total" in abstained
    assert "line_items[1].quantity" in abstained


def test_docling_semantic_adapter_returns_worker_candidates_without_canonicalizing():
    response = WorkerResponse(
        request_id="semantic_doc_semantic",
        success=True,
        actual_parser_id="docling_semantic",
        actual_parser_version="test",
        semantic_result_dict={
            "extractor_id": "docling_semantic",
            "extractor_version": "test",
            "document_id": "doc_semantic",
            "family": "sales_invoice",
            "success": True,
            "candidates": [
                {
                    "field_path": "common.document_number",
                    "value": "INV-X",
                    "raw_value": "INV-X",
                    "source_method": "docling_semantic",
                    "status": "proposed",
                    "evidence_hints": [{"page_number": 1}],
                }
            ],
            "abstained_fields": ["common.grand_total"],
        },
    )
    fake = FakeWorkerClient(response)
    extractor = DoclingSemanticExtractor(worker_client=fake)
    result = extractor.extract(_request())

    assert result.success
    assert result.candidates[0].field_path == "common.document_number"
    assert result.abstained_fields == ["common.grand_total"]
    worker_request, _ = fake.requests[0]
    assert worker_request.parser_id == "docling_semantic"
    assert worker_request.operation == "extract"
    assert worker_request.allow_model_download is False
    assert worker_request.options["schema_name"] == "SalesInvoicePayload"


def test_docling_semantic_adapter_caps_duplicate_page_candidates():
    response = WorkerResponse(
        request_id="semantic_doc_semantic",
        success=True,
        actual_parser_id="docling_semantic",
        semantic_result_dict={
            "extractor_id": "docling_semantic",
            "document_id": "doc_semantic",
            "family": "sales_invoice",
            "candidates": [
                {
                    "field_path": "common.document_number",
                    "value": "INV-A",
                    "source_method": "docling_semantic",
                    "evidence_hints": [{"page_number": 1}],
                },
                {
                    "field_path": "common.document_number",
                    "value": "INV-B",
                    "source_method": "docling_semantic",
                    "evidence_hints": [{"page_number": 2}],
                },
            ],
        },
    )
    result = DoclingSemanticExtractor(worker_client=FakeWorkerClient(response)).extract(_request())
    assert len(result.candidates) == 1
    assert "CANDIDATE_LIMIT_APPLIED" in result.warnings


def test_docling_semantic_adapter_rejects_unregistered_schema():
    request = _request().model_copy(
        update={"target_schema_name": "SomeOtherSalesSchema"}
    )
    result = DoclingSemanticExtractor(
        worker_client=FakeWorkerClient(
            WorkerResponse(
                request_id="unused",
                success=True,
                actual_parser_id="docling_semantic",
            )
        )
    ).extract(request)
    assert not result.success
    assert result.error_code == "UNSUPPORTED_SEMANTIC_SCHEMA"


def test_docling_semantic_worker_script_is_explicitly_registered():
    assert resolve_worker_script("docling_semantic").endswith("docling_semantic_worker.py")


def test_worker_response_accepts_semantic_result_payload():
    response = WorkerResponse(
        request_id="r1",
        success=True,
        actual_parser_id="docling_semantic",
        semantic_result_dict={"safe": True},
    )
    assert response.semantic_result_dict == {"safe": True}
