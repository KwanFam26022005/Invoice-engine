"""Business validation runner enforcing financial rules and document integrity."""

from decimal import Decimal
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict

from document_benchmark.core.contracts import CanonicalExtractionResult
from document_benchmark.core.statuses import DocumentFamily, Severity


class ValidationIssue(BaseModel):
    """Structured validation issue item."""

    model_config = ConfigDict(extra="ignore")

    code: str
    severity: Severity
    field_path: str
    expected: Optional[str] = None
    actual: Optional[str] = None
    message: str
    source_engine: str = ""


class ValidationRunner:
    """Executes business domain validation rules on CanonicalExtractionResult."""

    def __init__(self, financial_tolerance: Decimal = Decimal("1.0")) -> None:
        self.tolerance = financial_tolerance

    def validate(self, canonical: CanonicalExtractionResult) -> List[ValidationIssue]:
        issues: List[ValidationIssue] = []
        payload = canonical.canonical_payload or {}
        engine = canonical.source_engine

        if canonical.document_family == DocumentFamily.INVOICE:
            issues.extend(self._validate_invoice(payload, engine))
        elif canonical.document_family == DocumentFamily.OFFICE_SUPPLY_REQUEST:
            issues.extend(self._validate_office_supply_request(payload, engine))
        elif canonical.document_family == DocumentFamily.SOFTWARE_PROPOSAL:
            issues.extend(self._validate_software_proposal(payload, engine))

        return issues

    def _validate_invoice(self, payload: Dict[str, Any], engine: str) -> List[ValidationIssue]:
        issues: List[ValidationIssue] = []

        # Required fields check
        if not payload.get("invoice_number"):
            issues.append(
                ValidationIssue(
                    code="MISSING_INVOICE_NUMBER",
                    severity=Severity.CRITICAL,
                    field_path="invoice_number",
                    message="Invoice number is missing or empty.",
                    source_engine=engine,
                )
            )

        if not payload.get("seller_name"):
            issues.append(
                ValidationIssue(
                    code="MISSING_SELLER_NAME",
                    severity=Severity.ERROR,
                    field_path="seller_name",
                    message="Seller name is missing.",
                    source_engine=engine,
                )
            )

        # Financial math check: subtotal - discount + vat_amount ≈ total_amount
        try:
            subtotal = Decimal(str(payload.get("subtotal"))) if payload.get("subtotal") is not None else None
            discount = Decimal(str(payload.get("discount_amount"))) if payload.get("discount_amount") is not None else Decimal(0)
            vat = Decimal(str(payload.get("vat_amount"))) if payload.get("vat_amount") is not None else Decimal(0)
            total = Decimal(str(payload.get("total_amount"))) if payload.get("total_amount") is not None else None

            if subtotal is not None and total is not None:
                expected_total = subtotal - discount + vat
                diff = abs(expected_total - total)
                if diff > self.tolerance:
                    issues.append(
                        ValidationIssue(
                            code="FINANCIAL_TOTAL_MISMATCH",
                            severity=Severity.CRITICAL,
                            field_path="total_amount",
                            expected=str(expected_total),
                            actual=str(total),
                            message=f"Financial equation failed: subtotal ({subtotal}) - discount ({discount}) + VAT ({vat}) = {expected_total}, but got total_amount = {total} (diff={diff}).",
                            source_engine=engine,
                        )
                    )
        except Exception as e:
            issues.append(
                ValidationIssue(
                    code="FINANCIAL_PARSE_ERROR",
                    severity=Severity.ERROR,
                    field_path="total_amount",
                    message=f"Failed to calculate financial math: {e}",
                    source_engine=engine,
                )
            )

        return issues

    def _validate_office_supply_request(
        self, payload: Dict[str, Any], engine: str
    ) -> List[ValidationIssue]:
        issues: List[ValidationIssue] = []
        items = payload.get("items", [])

        if not items:
            issues.append(
                ValidationIssue(
                    code="EMPTY_ITEMS_LIST",
                    severity=Severity.WARNING,
                    field_path="items",
                    message="Office supply request contains no line items.",
                    source_engine=engine,
                )
            )

        for idx, item in enumerate(items, start=1):
            try:
                qty = Decimal(str(item.get("requested_quantity"))) if item.get("requested_quantity") is not None else None
                price = Decimal(str(item.get("unit_price"))) if item.get("unit_price") is not None else None
                amt = Decimal(str(item.get("amount"))) if item.get("amount") is not None else None

                if qty is not None and price is not None and amt is not None:
                    expected_amt = qty * price
                    if abs(expected_amt - amt) > self.tolerance:
                        issues.append(
                            ValidationIssue(
                                code="ITEM_MATH_MISMATCH",
                                severity=Severity.WARNING,
                                field_path=f"items[{idx}].amount",
                                expected=str(expected_amt),
                                actual=str(amt),
                                message=f"Item math failed: quantity ({qty}) × unit_price ({price}) = {expected_amt}, but got {amt}.",
                                source_engine=engine,
                            )
                        )
            except Exception:
                pass

        return issues

    def _validate_software_proposal(
        self, payload: Dict[str, Any], engine: str
    ) -> List[ValidationIssue]:
        issues: List[ValidationIssue] = []

        if not payload.get("software_name"):
            issues.append(
                ValidationIssue(
                    code="MISSING_SOFTWARE_NAME",
                    severity=Severity.CRITICAL,
                    field_path="software_name",
                    message="Software proposal is missing software_name.",
                    source_engine=engine,
                )
            )

        try:
            cost = Decimal(str(payload.get("estimated_cost"))) if payload.get("estimated_cost") is not None else None
            if cost is not None and cost < Decimal(0):
                issues.append(
                    ValidationIssue(
                        code="NEGATIVE_ESTIMATED_COST",
                        severity=Severity.ERROR,
                        field_path="estimated_cost",
                        actual=str(cost),
                        message="Estimated cost cannot be negative.",
                        source_engine=engine,
                    )
                )
        except Exception:
            pass

        return issues
