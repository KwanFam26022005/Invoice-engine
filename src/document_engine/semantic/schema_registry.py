"""Semantic schema registry for local schema-conditioned extraction canaries."""

from copy import deepcopy
from typing import Any, Dict

from pydantic import BaseModel, Field

from document_engine.core.models import DocumentFamilyType


class SemanticSchemaSpec(BaseModel):
    family: DocumentFamilyType
    schema_name: str = Field(min_length=1)
    template: Dict[str, Any]

    def template_copy(self) -> Dict[str, Any]:
        return deepcopy(self.template)


_PARTY_TEMPLATE = {"name": "string", "tax_id": "string", "address": "string"}

_COMMON_TEMPLATE = {
    "document_number": "string",
    "document_series": "string",
    "issue_date": "string",
    "currency": "string",
    "seller": _PARTY_TEMPLATE,
    "buyer": _PARTY_TEMPLATE,
    "billing_period": "string",
    "subtotal": "float",
    "discount": "float",
    "tax_amount": "float",
    "grand_total": "float",
}

_REGISTRY = {
    DocumentFamilyType.SALES_INVOICE: SemanticSchemaSpec(
        family=DocumentFamilyType.SALES_INVOICE,
        schema_name="SalesInvoicePayload",
        template={
            "common": _COMMON_TEMPLATE,
            "line_items": [{
                "description": "string", "code": "string", "unit": "string",
                "quantity": "float", "unit_price": "float", "discount": "float",
                "tax_rate": "float", "tax_amount": "float", "amount": "float",
            }],
        },
    ),
    DocumentFamilyType.UTILITY_CONSUMPTION_INVOICE: SemanticSchemaSpec(
        family=DocumentFamilyType.UTILITY_CONSUMPTION_INVOICE,
        schema_name="UtilityConsumptionInvoicePayload",
        template={
            "common": _COMMON_TEMPLATE,
            "service_location": "string",
            "contract_number": "string",
            "meter_readings": [{
                "meter_number": "string", "measurement_type": "string", "unit": "string",
                "opening_reading": "float", "closing_reading": "float",
                "conversion_factor": "float", "consumption": "float",
            }],
            "pricing_tiers": [{
                "tier_name": "string", "quantity": "float", "unit": "string",
                "unit_price": "float", "amount": "float",
            }],
        },
    ),
    DocumentFamilyType.TAX_WITHHOLDING_CERTIFICATE: SemanticSchemaSpec(
        family=DocumentFamilyType.TAX_WITHHOLDING_CERTIFICATE,
        schema_name="TaxWithholdingCertificatePayload",
        template={
            "form_number": "string", "serial_number": "string",
            "certificate_number": "string", "income_paying_organization": _PARTY_TEMPLATE,
            "recipient": _PARTY_TEMPLATE, "income_type": "string", "payment_period": "string",
            "total_taxable_income": "float", "total_tax_calculation_income": "float",
            "withheld_tax": "float", "signature_date": "string", "lookup_code": "string",
        },
    ),
}


def get_semantic_schema(family: DocumentFamilyType, target_schema_name: str | None = None) -> SemanticSchemaSpec:
    spec = _REGISTRY.get(family)
    if spec is None:
        raise KeyError(f"No semantic extraction schema registered for family: {family.value}")
    if target_schema_name and target_schema_name != spec.schema_name:
        raise KeyError(
            f"Requested semantic schema '{target_schema_name}' does not match registered schema "
            f"'{spec.schema_name}' for family '{family.value}'."
        )
    return spec.model_copy(deep=True)


def supports_semantic_schema(family: DocumentFamilyType, target_schema_name: str | None = None) -> bool:
    try:
        get_semantic_schema(family, target_schema_name)
        return True
    except KeyError:
        return False
