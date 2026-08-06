"""Canonical schemas package."""

from document_benchmark.schemas.common import DocumentEnvelope
from document_benchmark.schemas.invoice import InvoiceCore, InvoiceLineItem
from document_benchmark.schemas.office_supply_request import OfficeSupplyItem, OfficeSupplyRequest
from document_benchmark.schemas.software_proposal import SoftwareProposal

__all__ = [
    "DocumentEnvelope",
    "InvoiceCore",
    "InvoiceLineItem",
    "OfficeSupplyItem",
    "OfficeSupplyRequest",
    "SoftwareProposal",
]
