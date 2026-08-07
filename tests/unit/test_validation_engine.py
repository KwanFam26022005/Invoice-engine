"""Unit tests for deterministic validation engine."""

from decimal import Decimal
from document_engine.core.models import DocumentFamilyType
from document_engine.schemas.family_schemas import (
    BusinessDocumentEnvelope,
    CommonDocumentFields,
    LineItem,
    MeterReading,
    SalesInvoicePayload,
    UtilityConsumptionInvoicePayload,
)
from document_engine.validation.validator import BusinessValidator


def test_validate_valid_sales_invoice():
    line1 = LineItem(
        description="Consulting Service",
        quantity=Decimal("10.0"),
        unit_price=Decimal("500000.00"),
        amount=Decimal("5000000.00"),
    )
    payload = SalesInvoicePayload(
        common=CommonDocumentFields(
            document_number="INV-001",
            subtotal=Decimal("5000000.00"),
            grand_total=Decimal("5000000.00"),
        ),
        line_items=[line1],
    )
    envelope = BusinessDocumentEnvelope(
        document_id="doc_valid_inv",
        document_family=DocumentFamilyType.SALES_INVOICE,
        payload=payload,
    )

    validator = BusinessValidator()
    res = validator.validate(envelope)

    assert res.is_valid is True
    assert res.requires_review is False
    assert len(res.issues) == 0


def test_validate_line_item_amount_mismatch():
    line1 = LineItem(
        description="Consulting Service",
        quantity=Decimal("10.0"),
        unit_price=Decimal("500000.00"),
        amount=Decimal("4000000.00"),  # Mismatch! 10 * 500k = 5M
    )
    payload = SalesInvoicePayload(
        common=CommonDocumentFields(document_number="INV-002"),
        line_items=[line1],
    )
    envelope = BusinessDocumentEnvelope(
        document_id="doc_bad_inv",
        document_family=DocumentFamilyType.SALES_INVOICE,
        payload=payload,
    )

    validator = BusinessValidator()
    res = validator.validate(envelope)

    assert res.is_valid is False
    assert res.requires_review is True
    assert any(i.code == "LINE_ITEM_AMOUNT_MISMATCH" for i in res.issues)


def test_validate_meter_reading_math():
    meter = MeterReading(
        meter_number="M-100",
        opening_reading=Decimal("100.0"),
        closing_reading=Decimal("250.0"),
        conversion_factor=Decimal("1.0"),
        consumption=Decimal("150.0"),  # 250 - 100 = 150 -> Valid!
    )
    payload = UtilityConsumptionInvoicePayload(
        common=CommonDocumentFields(document_number="UTIL-001"),
        meter_readings=[meter],
    )
    envelope = BusinessDocumentEnvelope(
        document_id="doc_meter_valid",
        document_family=DocumentFamilyType.UTILITY_CONSUMPTION_INVOICE,
        payload=payload,
    )

    validator = BusinessValidator()
    res = validator.validate(envelope)
    assert res.is_valid is True
