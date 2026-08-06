"""Date normalizer standardizing dates into ISO yyyy-MM-dd format."""

from datetime import datetime
import re
from typing import Optional


def normalize_date(date_str: str) -> Optional[str]:
    """Parse date string into ISO 8601 YYYY-MM-DD format."""
    if not date_str:
        return None

    cleaned = str(date_str).strip()

    # Extract date patterns
    # 1. YYYY-MM-DD or YYYY/MM/DD
    m1 = re.search(r"(\d{4})[\/\-\.](\d{1,2})[\/\-\.](\d{1,2})", cleaned)
    if m1:
        y, m, d = int(m1.group(1)), int(m1.group(2)), int(m1.group(3))
        try:
            return datetime(y, m, d).strftime("%Y-%m-%d")
        except ValueError:
            pass

    # 2. DD/MM/YYYY or DD-MM-YYYY or DD.MM.YYYY
    m2 = re.search(r"(\d{1,2})[\/\-\.](\d{1,2})[\/\-\.](\d{4})", cleaned)
    if m2:
        d, m, y = int(m2.group(1)), int(m2.group(2)), int(m2.group(3))
        try:
            return datetime(y, m, d).strftime("%Y-%m-%d")
        except ValueError:
            pass

    # 3. Vietnamese textual date: Ngày 10 tháng 05 năm 2024
    m3 = re.search(
        r"Ngày\s*(\d{1,2})\s*tháng\s*(\d{1,2})\s*năm\s*(\d{4})",
        cleaned,
        re.IGNORECASE,
    )
    if m3:
        d, m, y = int(m3.group(1)), int(m3.group(2)), int(m3.group(3))
        try:
            return datetime(y, m, d).strftime("%Y-%m-%d")
        except ValueError:
            pass

    return None
