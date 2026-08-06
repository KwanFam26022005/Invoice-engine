"""Canonical Pydantic schema for Office Supply Request documents."""

from decimal import Decimal
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field


class OfficeSupplyItem(BaseModel):
    """Line item within an office supply request."""

    model_config = ConfigDict(extra="ignore")

    line_number: Optional[int] = None
    item_code: Optional[str] = None
    description: Optional[str] = None
    unit: Optional[str] = None
    requested_quantity: Optional[Decimal] = None
    unit_price: Optional[Decimal] = None
    amount: Optional[Decimal] = None
    note: Optional[str] = None


class OfficeSupplyRequest(BaseModel):
    """Canonical office supply request document payload."""

    model_config = ConfigDict(extra="ignore")

    request_title: Optional[str] = None
    request_date: Optional[str] = None
    requester_name: Optional[str] = None
    requester_department: Optional[str] = None
    receiving_department: Optional[str] = None
    total_amount: Optional[Decimal] = None
    items: list[OfficeSupplyItem] = Field(default_factory=list)
    approval_roles: list[str] = Field(default_factory=list)
