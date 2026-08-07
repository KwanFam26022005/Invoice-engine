"""Unit tests for deterministic field normalizers."""

from decimal import Decimal
from document_engine.extraction.normalizer import (
    normalize_container_number,
    normalize_tax_id,
    parse_date,
    parse_decimal,
)


def test_normalize_tax_id():
    val, status, _warnings = normalize_tax_id("0101234567")
    assert val == "0101234567"
    assert status == "valid"

    val_dash, status, _warnings = normalize_tax_id("0101234567-001")
    assert val_dash == "0101234567-001"
    assert status == "valid"


def test_parse_decimal_vietnamese_formats():
    # 1.234.567
    v1, _s1, _ = parse_decimal("1.234.567")
    assert v1 == Decimal(1234567)

    # 1,234,567
    v2, _s2, _ = parse_decimal("1,234,567")
    assert v2 == Decimal(1234567)

    # 1 234 567
    v3, _s3, _ = parse_decimal("1 234 567")
    assert v3 == Decimal(1234567)

    # 1.234.567 đ
    v4, _s4, _ = parse_decimal("1.234.567 đ")
    assert v4 == Decimal(1234567)

    # VND 1,234,567
    v5, _s5, _ = parse_decimal("VND 1,234,567")
    assert v5 == Decimal(1234567)


def test_parse_date():
    d1, _s1, _ = parse_date("15/08/2026")
    assert d1 == "2026-08-15"

    d2, _s2, _ = parse_date("Ngày 15 tháng 08 năm 2026")
    assert d2 == "2026-08-15"

    d3, _s3, _ = parse_date("2026-08-15")
    assert d3 == "2026-08-15"


def test_normalize_container_number():
    c1, s1, _ = normalize_container_number("tcnu 1234567")
    assert c1 == "TCNU1234567"
    assert s1 == "valid"
