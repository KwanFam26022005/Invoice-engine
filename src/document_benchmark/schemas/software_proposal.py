"""Canonical Pydantic schema for Software Proposal documents."""

from decimal import Decimal
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field


class SoftwareProposal(BaseModel):
    """Canonical software proposal document payload."""

    model_config = ConfigDict(extra="ignore")

    proposal_title: Optional[str] = None
    proposal_date: Optional[str] = None
    requester_name: Optional[str] = None
    requester_department: Optional[str] = None
    software_name: Optional[str] = None
    supplier_name: Optional[str] = None
    purpose: Optional[str] = None
    number_of_users: Optional[int] = None
    license_type: Optional[str] = None
    subscription_start: Optional[str] = None
    subscription_end: Optional[str] = None
    estimated_cost: Optional[Decimal] = None
    currency: str = "VND"
    justification: Optional[str] = None
    approval_roles: list[str] = Field(default_factory=list)
