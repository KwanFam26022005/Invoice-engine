"""Extraction mapper converts DocumentIR into canonical BusinessDocumentEnvelope."""

from datetime import datetime, timezone
from decimal import Decimal
import re
from typing import Any, Dict, List, Optional, Tuple

from document_engine.classification.classifier import ClassificationResult
from document_engine.core.models import DocumentFamilyType, SourceFormatType
from document_engine.extraction.normalizer import (
    normalize_tax_id,
    parse_date,
    parse_decimal,
)
from document_engine.ir.models import DocumentIR, EvidenceReference
from document_engine.schemas.family_schemas import (
    BusinessDocumentEnvelope,
    CommonDocumentFields,
    ContainerRecord,
    FieldCandidate,
    LineItem,
    MeterReading,
    Party,
    PortServiceInvoicePayload,
    PricingTier,
    ReceiptPayload,
    SalesInvoicePayload,
    ServiceRecord,
    ServiceVolumeInvoicePayload,
    SupportingStatementPayload,
    TaxWithholdingCertificatePayload,
    UnknownBusinessDocumentPayload,
    UtilityConsumptionInvoicePayload,
)


class DocumentMapper:
    def map_to_envelope(
        self, document_ir: DocumentIR, classification: ClassificationResult
    ) -> BusinessDocumentEnvelope:
        full_text = document_ir.full_text
        doc_id = document_ir.document_id
        family = classification.document_family

        field_candidates: Dict[str, FieldCandidate] = {}

        # Common extraction heuristics
        doc_number, doc_num_ev = self._extract_document_number(document_ir)
        issue_date, date_ev = self._extract_date(document_ir)
        seller_party = self._extract_seller(document_ir)
        buyer_party = self._extract_buyer(document_ir)
        grand_total, total_ev = self._extract_grand_total(document_ir)

        common = CommonDocumentFields(
            document_number=doc_number,
            issue_date=issue_date,
            seller=seller_party,
            buyer=buyer_party,
            grand_total=grand_total,
        )

        if doc_number:
            field_candidates["document_number"] = FieldCandidate(
                value=doc_number,
                raw_value=doc_number,
                evidence_references=doc_num_ev,
            )

        if issue_date:
            field_candidates["issue_date"] = FieldCandidate(
                value=issue_date,
                raw_value=issue_date,
                evidence_references=date_ev,
            )

        if grand_total is not None:
            field_candidates["grand_total"] = FieldCandidate(
                value=str(grand_total),
                raw_value=str(grand_total),
                evidence_references=total_ev,
            )

        payload = self._build_payload(family, common, document_ir)

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

    def _extract_document_number(
        self, document_ir: DocumentIR
    ) -> Tuple[Optional[str], List[EvidenceReference]]:
        text = document_ir.full_text
        m = re.search(
            r"(?:số|so|invoice no|no\.?)\s*:\s*([A-Za-z0-9\/\-]+)", text, re.IGNORECASE
        )
        if m:
            val = m.group(1).strip()
            ev = EvidenceReference(
                document_id=document_ir.document_id,
                page_number=1,
                source_text=m.group(0),
                parser_id=document_ir.provenance.parser_id,
            )
            return val, [ev]
        return None, []

    def _extract_date(
        self, document_ir: DocumentIR
    ) -> Tuple[Optional[str], List[EvidenceReference]]:
        text = document_ir.full_text
        val, status, _ = parse_date(text)
        if val:
            ev = EvidenceReference(
                document_id=document_ir.document_id,
                page_number=1,
                source_text=val,
                parser_id=document_ir.provenance.parser_id,
            )
            return val, [ev]
        return None, []

    def _extract_seller(self, document_ir: DocumentIR) -> Party:
        text = document_ir.full_text
        m_tax = re.search(
            r"(?:mst|mã số thuế|tax id)\s*(?:bán|bên bán)?\s*:\s*([\d\-]+)",
            text,
            re.IGNORECASE,
        )
        tax_id, _, _ = normalize_tax_id(m_tax.group(1)) if m_tax else (None, "", [])
        return Party(tax_id=tax_id)

    def _extract_buyer(self, document_ir: DocumentIR) -> Party:
        text = document_ir.full_text
        m_tax = re.search(
            r"(?:mst|mã số thuế|tax id)\s*(?:mua|bên mua)?\s*:\s*([\d\-]+)",
            text,
            re.IGNORECASE,
        )
        tax_id, _, _ = normalize_tax_id(m_tax.group(1)) if m_tax else (None, "", [])
        return Party(tax_id=tax_id)

    def _extract_grand_total(
        self, document_ir: DocumentIR
    ) -> Tuple[Optional[Decimal], List[EvidenceReference]]:
        text = document_ir.full_text
        m = re.search(
            r"(?:tổng cộng|tong cong|total|tổng tiền thanh toán)\s*:\s*([\d\.,\s]+)",
            text,
            re.IGNORECASE,
        )
        if m:
            val, status, _ = parse_decimal(m.group(1))
            if val is not None:
                ev = EvidenceReference(
                    document_id=document_ir.document_id,
                    page_number=1,
                    source_text=m.group(0),
                    parser_id=document_ir.provenance.parser_id,
                )
                return val, [ev]
        return None, []

    def _build_payload(
        self,
        family: DocumentFamilyType,
        common: CommonDocumentFields,
        document_ir: DocumentIR,
    ) -> Any:
        if family == DocumentFamilyType.SALES_INVOICE:
            return SalesInvoicePayload(common=common)
        elif family == DocumentFamilyType.UTILITY_CONSUMPTION_INVOICE:
            return UtilityConsumptionInvoicePayload(common=common)
        elif family == DocumentFamilyType.SERVICE_VOLUME_INVOICE:
            return ServiceVolumeInvoicePayload(common=common)
        elif family == DocumentFamilyType.PORT_SERVICE_INVOICE:
            return PortServiceInvoicePayload(common=common)
        elif family == DocumentFamilyType.RECEIPT:
            return ReceiptPayload(common=common)
        elif family == DocumentFamilyType.TAX_WITHHOLDING_CERTIFICATE:
            return TaxWithholdingCertificatePayload(common=common)
        elif family == DocumentFamilyType.SUPPORTING_STATEMENT:
            return SupportingStatementPayload(common=common)
        else:
            return UnknownBusinessDocumentPayload(
                common=common,
                review_notes=["Unidentified document family routed to review."],
            )
