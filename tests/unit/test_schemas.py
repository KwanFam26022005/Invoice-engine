"""Unit tests for canonical schemas with Decimal precision."""

from decimal import Decimal
from document_benchmark.schemas.invoice import InvoiceCore, InvoiceLineItem


def test_invoice_core_decimal_precision():
    item = InvoiceLineItem(
        line_number=1,
        description="Dịch vụ vận tải container",
        quantity=Decimal("2.5"),
        unit_price=Decimal("4000000.00"),
        amount_after_tax=Decimal("10000000.00"),
    )
    inv = InvoiceCore(
        invoice_number="0001234",
        seller_tax_id="0101234567",
        subtotal=Decimal("10000000.00"),
        vat_amount=Decimal("1000000.00"),
        total_amount=Decimal("11000000.00"),
        line_items=[item],
    )

    assert isinstance(inv.subtotal, Decimal)
    assert inv.subtotal == Decimal("10000000.00")
    assert inv.total_amount == Decimal("11000000.00")
    assert inv.line_items[0].quantity == Decimal("2.5")
