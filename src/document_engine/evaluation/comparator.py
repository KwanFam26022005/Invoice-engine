"""Deterministic field value comparator for exact and normalized evaluation."""

from decimal import Decimal
import unicodedata
from typing import Any, Tuple

from document_engine.extraction.normalizer import normalize_tax_id, parse_decimal


def compare_values(
    expected: Any,
    actual: Any,
    field_path: str = "",
    tolerance: float = 0.01,
) -> Tuple[bool, bool]:
    """Compare expected vs actual field value.

    Returns:
        (exact_match: bool, normalized_match: bool)
    """
    if expected is None and actual is None:
        return True, True
    if expected is None or actual is None:
        return False, False

    # Exact comparison
    exact_match = (expected == actual) or (str(expected).strip() == str(actual).strip())
    if exact_match:
        return True, True

    # Domain-specific normalized comparison
    exp_str = str(expected).strip()
    act_str = str(actual).strip()

    # Tax ID comparison
    if "tax_id" in field_path.lower():
        norm_exp, _, _ = normalize_tax_id(exp_str)
        norm_act, _, _ = normalize_tax_id(act_str)
        if norm_exp and norm_act:
            norm_match = (norm_exp == norm_act)
            return exact_match, norm_match

    # Numeric / Decimal comparison
    exp_dec = expected if isinstance(expected, Decimal) else (Decimal(str(expected)) if isinstance(expected, (int, float)) else parse_decimal(exp_str)[0])
    act_dec = actual if isinstance(actual, Decimal) else (Decimal(str(actual)) if isinstance(actual, (int, float)) else parse_decimal(act_str)[0])

    if exp_dec is not None and act_dec is not None:
        diff = abs(exp_dec - act_dec)
        norm_match = (diff <= Decimal(str(tolerance)))
        return exact_match, norm_match

    # String trimming and Unicode NFC normalization
    norm_exp_str = unicodedata.normalize("NFC", exp_str.lower())
    norm_act_str = unicodedata.normalize("NFC", act_str.lower())
    norm_match = (norm_exp_str == norm_act_str)

    return exact_match, norm_match
