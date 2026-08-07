"""Extraction mapper converts DocumentIR into canonical BusinessDocumentEnvelope using specialized family mappers."""

from datetime import datetime, timezone
from typing import Any, Dict, Optional

from document_engine.classification.classifier import ClassificationResult
from document_engine.core.models import DocumentFamilyType, SourceFormatType
from document_engine.extraction.candidate import FamilyCompletenessReport
from document_engine.extraction.family_mappers.sales_invoice import SalesInvoiceMapper
from document_engine.extraction.family_mappers.tax_withholding import TaxWithholdingMapper
from document_engine.extraction.family_mappers.utility_consumption import UtilityConsumptionMapper
from document_engine.ir.models import DocumentIR
from document_engine.schemas.family_schemas import (
    BusinessDocumentEnvelope,
    FieldCandidate,
    PortServiceInvoicePayload,
    ReceiptPayload,
    ServiceVolumeInvoicePayload,
    SupportingStatementPayload,
    UnknownBusinessDocumentPayload,
)


class DocumentMapper:
    def __init__(self):
        self.sales_mapper = SalesInvoiceMapper()
        self.utility_mapper = UtilityConsumptionMapper()
        self.tax_mapper = TaxWithholdingMapper()

    def map_to_envelope(
        self, document_ir: DocumentIR, classification: ClassificationResult
    ) -> BusinessDocumentEnvelope:
        doc_id = document_ir.document_id
        family = classification.document_family

        payload, field_candidates = self._build_payload_and_candidates(family, document_ir)

        source_fmt = (
            SourceFormatType.SCANNED_PAPER
            if document_ir.profile.requires_ocr
            else SourceFormatType.ELECTRONIC_DOCUMENT
        )

        return BusinessDocumentEnvelope(
            document_id=doc_id,
            document_family=family,
            source_format=source_fmt,
            pdf_profile=document_ir.profile.pdf_profile.value,
            created_at=datetime.now(timezone.utc).isoformat(),
            payload=payload,
            field_candidates=field_candidates,
            provenance_parser_id=document_ir.provenance.parser_id,
            provenance_parser_version=document_ir.provenance.parser_version,
        )

    def evaluate_completeness(
        self, envelope: BusinessDocumentEnvelope, document_ir: Optional[DocumentIR] = None
    ) -> FamilyCompletenessReport:
        family = envelope.document_family
        field_candidates = envelope.field_candidates
        full_text = document_ir.full_text if document_ir else ""

        if family == DocumentFamilyType.SALES_INVOICE:
            reqs = ["document_number", "issue_date", "grand_total"]
        elif family == DocumentFamilyType.UTILITY_CONSUMPTION_INVOICE:
            reqs = ["billing_period", "grand_total"]
        elif family == DocumentFamilyType.TAX_WITHHOLDING_CERTIFICATE:
            reqs = ["certificate_number", "withheld_tax"]
        else:
            reqs = ["document_number", "grand_total"]

        return FamilyCompletenessReport.evaluate(
            family.value, reqs, field_candidates, full_text
        )

    def _build_payload_and_candidates(
        self, family: DocumentFamilyType, document_ir: DocumentIR
    ) -> tuple[Any, Dict[str, FieldCandidate]]:
        if family == DocumentFamilyType.SALES_INVOICE:
            return self.sales_mapper.map(document_ir)
        elif family == DocumentFamilyType.UTILITY_CONSUMPTION_INVOICE:
            return self.utility_mapper.map(document_ir)
        elif family == DocumentFamilyType.TAX_WITHHOLDING_CERTIFICATE:
            return self.tax_mapper.map(document_ir)
        elif family == DocumentFamilyType.SERVICE_VOLUME_INVOICE:
            return ServiceVolumeInvoicePayload(), {}
        elif family == DocumentFamilyType.PORT_SERVICE_INVOICE:
            return PortServiceInvoicePayload(), {}
        elif family == DocumentFamilyType.RECEIPT:
            return ReceiptPayload(), {}
        elif family == DocumentFamilyType.SUPPORTING_STATEMENT:
            return SupportingStatementPayload(), {}
        else:
            return UnknownBusinessDocumentPayload(
                review_notes=["Unidentified document family routed to review."]
            ), {}
