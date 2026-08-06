"""Unit tests for normalization layer (number, date, tax_id, text)."""

from decimal import Decimal
from document_benchmark.normalization.date_normalizer import normalize_date
from document_benchmark.normalization.number_normalizer import normalize_number
from document_benchmark.normalization.tax_id_normalizer import normalize_tax_id
from document_benchmark.normalization.text_normalizer import normalize_text


def test_normalize_number_formats():
    assert normalize_number("1.250.000") == Decimal(1250000)
    assert normalize_number("1,250,000") == Decimal(1250000)
    assert normalize_number("1250000") == Decimal(1250000)
    assert normalize_number("1,250.50") == Decimal("1250.50")
    assert normalize_number("1.250,50") == Decimal("1250.50")
    assert normalize_number("1.5") == Decimal("1.5")
    assert normalize_number("1,5") == Decimal("1.5")


def test_normalize_date_formats():
    assert normalize_date("10/05/2024") == "2024-05-10"
    assert normalize_date("10-05-2024") == "2024-05-10"
    assert normalize_date("2024-05-10") == "2024-05-10"
    assert normalize_date("Ngày 10 tháng 05 năm 2024") == "2024-05-10"


def test_normalize_tax_id_formats():
    assert normalize_tax_id("0101234567") == "0101234567"
    assert normalize_tax_id("010 123 4567") == "0101234567"
    assert normalize_tax_id("0101234567-001") == "0101234567-001"


def test_normalize_text_unicode():
    raw = "  CÔNG   TY  TNHH   "
    assert normalize_text(raw) == "CÔNG TY TNHH"
