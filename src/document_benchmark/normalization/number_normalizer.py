"""High-precision Decimal number normalizer handling Vietnamese and International currency formats."""

from decimal import Decimal, InvalidOperation
import re
from typing import Optional


def normalize_number(value_str: str) -> Optional[Decimal]:
    """Parse numeric / monetary string into high-precision Decimal."""
    if not value_str:
        return None

    cleaned = str(value_str).strip()

    # Remove currency symbols, letters, spaces
    cleaned = re.sub(r"[^\d\.,\-]", "", cleaned)

    if not cleaned or cleaned == "-":
        return None

    # Handle negative sign
    is_negative = cleaned.startswith("-")
    if is_negative:
        cleaned = cleaned[1:]

    # Inspect comma and period positions
    has_period = "." in cleaned
    has_comma = "," in cleaned

    normalized_str = cleaned

    if has_period and has_comma:
        last_period = cleaned.rfind(".")
        last_comma = cleaned.rfind(",")
        if last_comma > last_period:
            # European/Vietnamese format: 1.250,50 -> 1250.50
            normalized_str = cleaned.replace(".", "").replace(",", ".")
        else:
            # US format: 1,250.50 -> 1250.50
            normalized_str = cleaned.replace(",", "")
    elif has_period:
        parts = cleaned.split(".")
        # If multiple periods (e.g. 1.250.000), treat periods as thousands separators
        if len(parts) > 2:
            normalized_str = cleaned.replace(".", "")
        elif len(parts) == 2:
            # Single period: 1.250 vs 1.5
            if len(parts[1]) == 3 and len(parts[0]) <= 3:
                # Likely thousands separator: 1.250 -> 1250
                normalized_str = cleaned.replace(".", "")
            else:
                # Decimal point: 1.5 -> 1.5
                normalized_str = cleaned
    elif has_comma:
        parts = cleaned.split(",")
        if len(parts) > 2:
            normalized_str = cleaned.replace(",", "")
        elif len(parts) == 2:
            if len(parts[1]) == 3 and len(parts[0]) <= 3:
                # Thousands separator: 1,250 -> 1250
                normalized_str = cleaned.replace(",", "")
            else:
                # Decimal comma: 1,5 -> 1.5
                normalized_str = cleaned.replace(",", ".")

    if is_negative:
        normalized_str = "-" + normalized_str

    try:
        return Decimal(normalized_str)
    except (InvalidOperation, TypeError):
        return None
