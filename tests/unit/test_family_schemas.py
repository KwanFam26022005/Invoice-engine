"""Unit tests for canonical business document schemas."""

from decimal import Decimal
from document_engine.core.models import DocumentFamilyType
from document_engine.schemas.family_schemas import (
    BusinessDocumentEnvelope,
    CommonDocumentFields,
    ContainerRecord,
    LineItem,
    Party,
    PortServiceInvoicePayload,
    SalesInvoicePayload,
    TaxWithholdingCertificatePayload,
)


def test_sales_invoice_schema_decimal():
    seller = Party(name="Seller Inc", tax_id="0101234567")
    buyer = Party(name="Buyer Inc", tax_id="0109876543")
    item = LineItem(
        description="Container Handling",
        quantity=Decimal("2.0"),
        unit_price=Decimal("1500000.00"),
        amount=Decimal("3000000.00"),
    )
    payload = SalesInvoicePayload(
        common=CommonDocumentFields(
            document_number="INV-2026-001",
            seller=seller,
            buyer=buyer,
            grand_total=Decimal("3000000.00"),
        ),
        line_items=[item],
    )

    envelope = BusinessDocumentEnvelope(
        document_id="doc_test123",
        document_family=DocumentFamilyType.SALES_INVOICE,
        payload=payload,
    )

    assert envelope.document_family == DocumentFamilyType.SALES_INVOICE
    assert envelope.payload.common.grand_total == Decimal("3000000.00")
    assert type(envelope.payload.line_items[0].amount) is Decimal


def test_tax_withholding_certificate_schema():
    payload = TaxWithholdingCertificatePayload(
        certificate_number="TNCN-2026-099",
        total_taxable_income=Decimal("50000000.00"),
        withheld_tax=Decimal("5000000.00"),
    )

    envelope = BusinessDocumentEnvelope(
        document_id="doc_tax123",
        document_family=DocumentFamilyType.TAX_WITHHOLDING_CERTIFICATE,
        payload=payload,
    )

    assert envelope.document_family == DocumentFamilyType.TAX_WITHHOLDING_CERTIFICATE
    assert envelope.payload.withheld_tax == Decimal("5000000.00")


def test_port_service_schema():
    cont = ContainerRecord(
        container_number="TCNU1234567",
        container_size="20",
        teu=Decimal("1.0"),
        amount=Decimal("2500000.00"),
    )
    payload = PortServiceInvoicePayload(
        container_records=[cont],
    )
    assert payload.container_records[0].container_number == "TCNU1234567"
