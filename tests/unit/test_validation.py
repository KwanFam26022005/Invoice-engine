"""Unit tests for business validation rules."""

from document_benchmark.core.contracts import CanonicalExtractionResult
from document_benchmark.core.statuses import DocumentFamily, Severity
from document_benchmark.validation.validation_runner import ValidationRunner


def test_invoice_validation_valid():
    can = CanonicalExtractionResult(
        document_id="doc_valid",
        document_family=DocumentFamily.INVOICE,
        canonical_payload={
            "invoice_number": "0001234",
            "seller_name": "Logistics Global",
            "subtotal": "10000000.00",
            "discount_amount": "0.00",
            "vat_amount": "1000000.00",
            "total_amount": "11000000.00",
        },
        source_engine="mock",
    )
    validator = ValidationRunner()
    issues = validator.validate(can)
    critical_issues = [i for i in issues if i.severity == Severity.CRITICAL]
    assert len(critical_issues) == 0


def test_invoice_validation_total_mismatch():
    can = CanonicalExtractionResult(
        document_id="doc_invalid",
        document_family=DocumentFamily.INVOICE,
        canonical_payload={
            "invoice_number": "0001234",
            "seller_name": "Logistics Global",
            "subtotal": "10000000.00",
            "discount_amount": "0.00",
            "vat_amount": "1000000.00",
            "total_amount": "99999999.00",  # Invalid total!
        },
        source_engine="mock",
    )
    validator = ValidationRunner()
    issues = validator.validate(can)
    mismatch = [i for i in issues if i.code == "FINANCIAL_TOTAL_MISMATCH"]
    assert len(mismatch) == 1
    assert mismatch[0].severity == Severity.CRITICAL
