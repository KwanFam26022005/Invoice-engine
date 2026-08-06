"""Canonical Pydantic schema for Invoice documents with Decimal financial fields."""

from decimal import Decimal
from typing import Any, Optional
from pydantic import BaseModel, ConfigDict, Field


class InvoiceLineItem(BaseModel):
    """Line item itemized within an invoice."""

    model_config = ConfigDict(extra="ignore")

    line_number: Optional[int] = None
    code: Optional[str] = None
    description: Optional[str] = None
    unit: Optional[str] = None
    quantity: Optional[Decimal] = None
    unit_price: Optional[Decimal] = None
    discount_amount: Optional[Decimal] = None
    amount_before_tax: Optional[Decimal] = None
    vat_rate: Optional[Decimal] = None
    vat_amount: Optional[Decimal] = None
    amount_after_tax: Optional[Decimal] = None
    attributes: dict[str, Any] = Field(default_factory=dict)


class InvoiceCore(BaseModel):
    """Core invoice payload conforming to financial standards."""

    model_config = ConfigDict(extra="ignore")

    invoice_number: Optional[str] = None
    invoice_series: Optional[str] = None
    invoice_date: Optional[str] = None  # ISO format yyyy-MM-dd
    invoice_type: Optional[str] = None
    seller_name: Optional[str] = None
    seller_tax_id: Optional[str] = None
    seller_address: Optional[str] = None
    buyer_name: Optional[str] = None
    buyer_tax_id: Optional[str] = None
    buyer_address: Optional[str] = None
    currency: str = "VND"
    exchange_rate: Optional[Decimal] = None
    subtotal: Optional[Decimal] = None
    discount_amount: Optional[Decimal] = Decimal(0)
    vat_amount: Optional[Decimal] = None
    total_amount: Optional[Decimal] = None
    payment_method: Optional[str] = None
    amount_in_words: Optional[str] = None
    line_items: list[InvoiceLineItem] = Field(default_factory=list)
