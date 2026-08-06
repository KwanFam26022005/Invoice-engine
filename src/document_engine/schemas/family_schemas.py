"""Canonical Business Document Schemas using Pydantic discriminated unions and Decimal precision."""

from decimal import Decimal
from typing import Any, Dict, List, Literal, Optional, Union
from pydantic import BaseModel, Field

from document_engine.core.models import DocumentFamilyType, SourceFormatType
from document_engine.ir.models import EvidenceReference


class FieldCandidate(BaseModel):
    value: Optional[Any] = None
    raw_value: Optional[str] = None
    normalized_value: Optional[str] = None
    confidence: float = 1.0
    evidence_references: List[EvidenceReference] = Field(default_factory=list)
    extraction_method: str = "native_text"  # native_text, ocr_text, table_cell, anchor_rule, computed, human_corrected
    warnings: List[str] = Field(default_factory=list)


class Party(BaseModel):
    name: Optional[str] = None
    tax_id: Optional[str] = None
    address: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    bank_account: Optional[str] = None


class LineItem(BaseModel):
    item_id: Optional[str] = None
    description: str = ""
    code: Optional[str] = None
    unit: Optional[str] = None
    quantity: Optional[Decimal] = None
    unit_price: Optional[Decimal] = None
    discount: Optional[Decimal] = None
    tax_rate: Optional[Decimal] = None
    tax_amount: Optional[Decimal] = None
    amount: Decimal = Field(default_factory=lambda: Decimal("0.00"))
    evidence: List[EvidenceReference] = Field(default_factory=list)


class TaxBreakdown(BaseModel):
    tax_rate: Decimal
    taxable_amount: Decimal
    tax_amount: Decimal


class MeterReading(BaseModel):
    meter_number: str = ""
    measurement_type: str = "electricity"  # electricity, water, gas
    unit: str = "kWh"
    opening_reading: Decimal = Field(default_factory=lambda: Decimal("0.0"))
    closing_reading: Decimal = Field(default_factory=lambda: Decimal("0.0"))
    conversion_factor: Decimal = Field(default_factory=lambda: Decimal("1.0"))
    consumption: Decimal = Field(default_factory=lambda: Decimal("0.0"))


class PricingTier(BaseModel):
    tier_name: str = ""
    quantity: Decimal = Field(default_factory=lambda: Decimal("0.0"))
    unit: str = "kWh"
    unit_price: Decimal = Field(default_factory=lambda: Decimal("0.00"))
    amount: Decimal = Field(default_factory=lambda: Decimal("0.00"))


class ServiceRecord(BaseModel):
    service_type: str = ""
    description: str = ""
    quantity: Decimal = Field(default_factory=lambda: Decimal("0.0"))
    unit: str = ""
    unit_price: Decimal = Field(default_factory=lambda: Decimal("0.00"))
    amount: Decimal = Field(default_factory=lambda: Decimal("0.00"))
    location: Optional[str] = None
    reference_number: Optional[str] = None


class ContainerRecord(BaseModel):
    container_number: str = ""
    container_size: str = "20"  # 20, 40, 45
    container_type: str = "GP"  # GP, HC, RF, OT
    teu: Decimal = Field(default_factory=lambda: Decimal("1.0"))
    gross_weight: Optional[Decimal] = None
    service_type: str = ""  # lift_on, lift_off, storage, gate_in, gate_out
    lift_count: int = 1
    storage_days: int = 0
    gate_in_time: Optional[str] = None
    gate_out_time: Optional[str] = None
    yard_location: Optional[str] = None
    amount: Decimal = Field(default_factory=lambda: Decimal("0.00"))


class CommonDocumentFields(BaseModel):
    document_number: Optional[str] = None
    document_series: Optional[str] = None
    issue_date: Optional[str] = None
    currency: str = "VND"
    seller: Party = Field(default_factory=Party)
    buyer: Party = Field(default_factory=Party)
    billing_period: Optional[str] = None
    subtotal: Optional[Decimal] = None
    discount: Optional[Decimal] = None
    tax_amount: Optional[Decimal] = None
    grand_total: Optional[Decimal] = None


# Family 1: Sales Invoice
class SalesInvoicePayload(BaseModel):
    document_family: Literal[DocumentFamilyType.SALES_INVOICE] = (
        DocumentFamilyType.SALES_INVOICE
    )
    common: CommonDocumentFields = Field(default_factory=CommonDocumentFields)
    line_items: List[LineItem] = Field(default_factory=list)
    tax_breakdown: List[TaxBreakdown] = Field(default_factory=list)


# Family 2: Utility Consumption Invoice
class UtilityConsumptionInvoicePayload(BaseModel):
    document_family: Literal[DocumentFamilyType.UTILITY_CONSUMPTION_INVOICE] = (
        DocumentFamilyType.UTILITY_CONSUMPTION_INVOICE
    )
    common: CommonDocumentFields = Field(default_factory=CommonDocumentFields)
    service_location: Optional[str] = None
    contract_number: Optional[str] = None
    meter_readings: List[MeterReading] = Field(default_factory=list)
    pricing_tiers: List[PricingTier] = Field(default_factory=list)


# Family 3: Service Volume Invoice
class ServiceVolumeInvoicePayload(BaseModel):
    document_family: Literal[DocumentFamilyType.SERVICE_VOLUME_INVOICE] = (
        DocumentFamilyType.SERVICE_VOLUME_INVOICE
    )
    common: CommonDocumentFields = Field(default_factory=CommonDocumentFields)
    service_records: List[ServiceRecord] = Field(default_factory=list)
    quantity_summary: Dict[str, Decimal] = Field(default_factory=dict)


# Family 4: Port Service Invoice
class PortServiceInvoicePayload(BaseModel):
    document_family: Literal[DocumentFamilyType.PORT_SERVICE_INVOICE] = (
        DocumentFamilyType.PORT_SERVICE_INVOICE
    )
    common: CommonDocumentFields = Field(default_factory=CommonDocumentFields)
    container_records: List[ContainerRecord] = Field(default_factory=list)
    service_records: List[ServiceRecord] = Field(default_factory=list)


# Family 5: Receipt
class ReceiptPayload(BaseModel):
    document_family: Literal[DocumentFamilyType.RECEIPT] = DocumentFamilyType.RECEIPT
    common: CommonDocumentFields = Field(default_factory=CommonDocumentFields)
    receipt_number: Optional[str] = None
    receipt_date: Optional[str] = None
    payer: Party = Field(default_factory=Party)
    payee: Party = Field(default_factory=Party)
    payment_method: Optional[str] = None
    reason: Optional[str] = None
    amount: Decimal = Field(default_factory=lambda: Decimal("0.00"))


# Family 6: Tax Withholding Certificate
class TaxWithholdingCertificatePayload(BaseModel):
    document_family: Literal[DocumentFamilyType.TAX_WITHHOLDING_CERTIFICATE] = (
        DocumentFamilyType.TAX_WITHHOLDING_CERTIFICATE
    )
    common: CommonDocumentFields = Field(default_factory=CommonDocumentFields)
    form_number: Optional[str] = None
    serial_number: Optional[str] = None
    certificate_number: Optional[str] = None
    income_paying_organization: Party = Field(default_factory=Party)
    recipient: Party = Field(default_factory=Party)
    income_type: Optional[str] = None
    payment_period: Optional[str] = None
    total_taxable_income: Decimal = Field(default_factory=lambda: Decimal("0.00"))
    total_tax_calculation_income: Decimal = Field(
        default_factory=lambda: Decimal("0.00")
    )
    withheld_tax: Decimal = Field(default_factory=lambda: Decimal("0.00"))
    signature_date: Optional[str] = None
    lookup_code: Optional[str] = None


# Family 7: Supporting Statement
class SupportingStatementPayload(BaseModel):
    document_family: Literal[DocumentFamilyType.SUPPORTING_STATEMENT] = (
        DocumentFamilyType.SUPPORTING_STATEMENT
    )
    common: CommonDocumentFields = Field(default_factory=CommonDocumentFields)
    statement_number: Optional[str] = None
    period: Optional[str] = None
    rows: List[Dict[str, Any]] = Field(default_factory=list)
    related_document_ids: List[str] = Field(default_factory=list)


# Family 8: Unknown Business Document
class UnknownBusinessDocumentPayload(BaseModel):
    document_family: Literal[DocumentFamilyType.UNKNOWN] = DocumentFamilyType.UNKNOWN
    common: CommonDocumentFields = Field(default_factory=CommonDocumentFields)
    detected_key_values: Dict[str, str] = Field(default_factory=dict)
    detected_tables: List[List[List[str]]] = Field(default_factory=list)
    detected_dates: List[str] = Field(default_factory=list)
    detected_amounts: List[Decimal] = Field(default_factory=list)
    review_notes: List[str] = Field(default_factory=list)


CanonicalPayload = Union[
    SalesInvoicePayload,
    UtilityConsumptionInvoicePayload,
    ServiceVolumeInvoicePayload,
    PortServiceInvoicePayload,
    ReceiptPayload,
    TaxWithholdingCertificatePayload,
    SupportingStatementPayload,
    UnknownBusinessDocumentPayload,
]


class BusinessDocumentEnvelope(BaseModel):
    document_id: str
    document_family: DocumentFamilyType
    source_format: SourceFormatType = SourceFormatType.ELECTRONIC_DOCUMENT
    pdf_profile: str = "native_pdf"
    created_at: str = ""
    payload: CanonicalPayload
    field_candidates: Dict[str, FieldCandidate] = Field(default_factory=dict)
    provenance_parser_id: str = ""
    provenance_parser_version: str = ""
