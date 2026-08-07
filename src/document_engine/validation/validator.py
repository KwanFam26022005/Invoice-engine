"""Deterministic business validation engine with Decimal precision and configurable tolerance."""

from decimal import Decimal
from typing import List, Optional
from pydantic import BaseModel, Field

from document_engine.core.models import DocumentFamilyType, ValidationSeverity
from document_engine.ir.models import EvidenceReference
from document_engine.schemas.family_schemas import (
    BusinessDocumentEnvelope,
    SalesInvoicePayload,
    TaxWithholdingCertificatePayload,
    UtilityConsumptionInvoicePayload,
)


class ValidationIssue(BaseModel):
    code: str
    severity: ValidationSeverity
    field_path: str
    message: str
    expected: Optional[str] = None
    actual: Optional[str] = None
    evidence: List[EvidenceReference] = Field(default_factory=list)
    review_required: bool = False


class ValidationResult(BaseModel):
    is_valid: bool
    requires_review: bool
    issues: List[ValidationIssue] = Field(default_factory=list)


class BusinessValidator:
    def __init__(self, tolerance: float = 0.01):
        self.tolerance = Decimal(str(tolerance))

    def validate(self, envelope: BusinessDocumentEnvelope) -> ValidationResult:
        issues: List[ValidationIssue] = []

        family = envelope.document_family
        payload = envelope.payload

        if family == DocumentFamilyType.UNKNOWN:
            issues.append(
                ValidationIssue(
                    code="UNKNOWN_DOCUMENT_FAMILY",
                    severity=ValidationSeverity.WARNING,
                    field_path="document_family",
                    message="Document family is unknown and requires manual review.",
                    review_required=True,
                )
            )
            return ValidationResult(
                is_valid=False, requires_review=True, issues=issues
            )

        # Generic common fields check
        common = getattr(payload, "common", None)
        if common:
            if not common.document_number:
                issues.append(
                    ValidationIssue(
                        code="MISSING_DOCUMENT_NUMBER",
                        severity=ValidationSeverity.WARNING,
                        field_path="common.document_number",
                        message="Document number is missing.",
                        review_required=True,
                    )
                )

            if common.grand_total is not None and common.grand_total < Decimal("0.00"):
                issues.append(
                    ValidationIssue(
                        code="NEGATIVE_GRAND_TOTAL",
                        severity=ValidationSeverity.ERROR,
                        field_path="common.grand_total",
                        message=f"Grand total cannot be negative: {common.grand_total}",
                        actual=str(common.grand_total),
                        review_required=True,
                    )
                )

        # Evidence requirement check: Every accepted candidate should have evidence
        for f_name, candidate in envelope.field_candidates.items():
            if candidate.value is not None and not candidate.evidence_references:
                issues.append(
                    ValidationIssue(
                        code="MISSING_EVIDENCE_FOR_FIELD",
                        severity=ValidationSeverity.WARNING,
                        field_path=f"field_candidates.{f_name}",
                        message=f"Extracted field '{f_name}' has no backing evidence reference.",
                        review_required=True,
                    )
                )

        # Family specific checks
        if isinstance(payload, SalesInvoicePayload):
            self._validate_sales_invoice(payload, issues)
        elif isinstance(payload, UtilityConsumptionInvoicePayload):
            self._validate_utility_invoice(payload, issues)
        elif isinstance(payload, TaxWithholdingCertificatePayload):
            self._validate_tax_certificate(payload, issues)

        has_errors = any(
            i.severity in (ValidationSeverity.ERROR, ValidationSeverity.CRITICAL)
            for i in issues
        )
        requires_review = (
            has_errors or any(i.review_required for i in issues)
        )

        return ValidationResult(
            is_valid=not has_errors,
            requires_review=requires_review,
            issues=issues,
        )

    def _validate_sales_invoice(
        self, payload: SalesInvoicePayload, issues: List[ValidationIssue]
    ) -> None:
        common = payload.common
        line_items = payload.line_items

        if line_items:
            calculated_subtotal = Decimal("0.00")
            for idx, item in enumerate(line_items):
                if item.quantity is not None and item.unit_price is not None and item.amount is not None:
                    calc_amount = item.quantity * item.unit_price
                    diff = abs(calc_amount - item.amount)
                    if diff > self.tolerance:
                        issues.append(
                            ValidationIssue(
                                code="LINE_ITEM_AMOUNT_MISMATCH",
                                severity=ValidationSeverity.ERROR,
                                field_path=f"line_items[{idx}].amount",
                                message=f"Line item {idx + 1} amount mismatch: {item.quantity} * {item.unit_price} = {calc_amount}, actual={item.amount}",
                                expected=str(calc_amount),
                                actual=str(item.amount),
                                review_required=True,
                            )
                        )
                if item.amount is not None:
                    calculated_subtotal += item.amount

            if common.subtotal is not None and calculated_subtotal > Decimal("0.00"):
                diff_sub = abs(calculated_subtotal - common.subtotal)
                if diff_sub > self.tolerance:
                    issues.append(
                        ValidationIssue(
                            code="SUBTOTAL_MISMATCH",
                            severity=ValidationSeverity.ERROR,
                            field_path="common.subtotal",
                            message=f"Subtotal mismatch: sum of line items ({calculated_subtotal}) != subtotal ({common.subtotal})",
                            expected=str(calculated_subtotal),
                            actual=str(common.subtotal),
                            review_required=True,
                        )
                    )

    def _validate_utility_invoice(
        self, payload: UtilityConsumptionInvoicePayload, issues: List[ValidationIssue]
    ) -> None:
        for idx, meter in enumerate(payload.meter_readings):
            if (
                meter.closing_reading is not None
                and meter.opening_reading is not None
                and meter.consumption is not None
            ):
                factor = meter.conversion_factor or Decimal("1.0")
                calc_consumption = (meter.closing_reading - meter.opening_reading) * factor
                diff = abs(calc_consumption - meter.consumption)
                if diff > self.tolerance:
                    issues.append(
                        ValidationIssue(
                            code="METER_CONSUMPTION_MISMATCH",
                            severity=ValidationSeverity.ERROR,
                            field_path=f"meter_readings[{idx}].consumption",
                            message=f"Meter {idx + 1} consumption math mismatch: ({meter.closing_reading} - {meter.opening_reading}) * {factor} = {calc_consumption}, actual={meter.consumption}",
                            expected=str(calc_consumption),
                            actual=str(meter.consumption),
                            review_required=True,
                        )
                    )

    def _validate_tax_certificate(
        self, payload: TaxWithholdingCertificatePayload, issues: List[ValidationIssue]
    ) -> None:
        if payload.withheld_tax is not None and payload.withheld_tax < Decimal("0.00"):
            issues.append(
                ValidationIssue(
                    code="NEGATIVE_WITHHELD_TAX",
                    severity=ValidationSeverity.ERROR,
                    field_path="withheld_tax",
                    message="Withheld tax amount cannot be negative.",
                    actual=str(payload.withheld_tax),
                    review_required=True,
                )
            )
