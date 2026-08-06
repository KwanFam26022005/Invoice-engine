"""Tax ID (Mã số thuế) normalizer."""

import re
from typing import Optional


def normalize_tax_id(tax_id_str: str) -> Optional[str]:
    """Clean spaces and presentation separators while keeping exact digits and branch dash."""
    if not tax_id_str:
        return None

    cleaned = str(tax_id_str).strip()
    # Replace whitespace and dot separators
    cleaned = re.sub(r"[\s\.]+", "", cleaned)

    # Check 10-digit or 13-digit MST pattern
    # 0101234567 or 0101234567-001 or 0101234567001
    m = re.match(r"^(\d{10})(?:[\-]?(\d{3}))?$", cleaned)
    if m:
        main_mst = m.group(1)
        branch = m.group(2)
        if branch:
            return f"{main_mst}-{branch}"
        return main_mst

    # Fallback to alphanumeric cleaning if non-standard
    fallback = re.sub(r"[^\w\-]", "", cleaned)
    return fallback or None
