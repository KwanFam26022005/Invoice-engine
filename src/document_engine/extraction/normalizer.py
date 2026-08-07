"""Deterministic field normalizers with explicit status and warning tracking."""

from decimal import Decimal, InvalidOperation
import re
import unicodedata
from typing import List, Optional, Tuple


def normalize_text(raw_text: Optional[str]) -> Tuple[str, str, List[str]]:
    if not raw_text:
        return "", "empty", []
    # Unicode NFC normalization and whitespace collapse
    text = unicodedata.normalize("NFC", raw_text)
    clean = re.sub(r"\s+", " ", text).strip()
    return clean, "valid", []


def normalize_tax_id(raw_tax_id: Optional[str]) -> Tuple[Optional[str], str, List[str]]:
    """Normalize Vietnamese Tax ID (10 digits or 13 digits with dash: XXXXXXXXXX-XXX)."""
    if not raw_tax_id:
        return None, "empty", []

    clean = re.sub(r"[^\d\-]", "", raw_tax_id.strip())
    warnings: List[str] = []

    # Check potential OCR errors without mutating digits
    if re.search(r"[OoSsIilL]", raw_tax_id):
        warnings.append(
            f"Tax ID contains potential OCR alpha confusion characters in '{raw_tax_id}'."
        )

    # Standard formats: 10 digits or 10 digits + '-' + 3 digits
    if re.match(r"^\d{10}$", clean) or re.match(r"^\d{10}\-\d{3}$", clean):
        return clean, "valid", warnings
    elif re.match(r"^\d{13}$", clean):
        formatted = f"{clean[:10]}-{clean[10:]}"
        return formatted, "valid", warnings

    warnings.append(f"Invalid Vietnamese Tax ID format: '{raw_tax_id}'")
    return clean, "invalid_format", warnings


def parse_decimal(
    raw_amount: Optional[str], default_currency: str = "VND"
) -> Tuple[Optional[Decimal], str, List[str]]:
    """Parse Vietnamese and international currency amounts safely into Decimal.

    Handles:
    - 1.234.567
    - 1,234,567
    - 1 234 567
    - 1.234.567 đ
    - VND 1,234,567
    - 1234567.89
    """
    if not raw_amount:
        return None, "empty", []

    warnings: List[str] = []
    clean = raw_amount.strip()

    # Remove currency symbols and letters
    clean_no_symbol = re.sub(r"[^\d.,\s\-]", "", clean).strip()
    if not clean_no_symbol:
        return None, "invalid", [f"No numeric characters found in '{raw_amount}'"]

    # Remove spaces
    clean_no_space = clean_no_symbol.replace(" ", "")

    # Handle Vietnamese period thousands dot separators: 1.234.567 or 1.234.567,89
    if clean_no_space.count(".") > 1:
        # Multiple dots -> period is thousands separator
        clean_norm = clean_no_space.replace(".", "").replace(",", ".")
    elif "," in clean_no_space and "." in clean_no_space:
        if clean_no_space.rfind(".") > clean_no_space.rfind(","):
            # e.g., 1,234,567.89
            clean_norm = clean_no_space.replace(",", "")
        else:
            # e.g., 1.234.567,89
            clean_norm = clean_no_space.replace(".", "").replace(",", ".")
    elif "," in clean_no_space:
        # Check if comma is decimal separator (e.g. 1234,50) or thousands separator (1,234,567)
        parts = clean_no_space.split(",")
        if len(parts) == 2 and len(parts[1]) in (1, 2):
            clean_norm = clean_no_space.replace(",", ".")
        else:
            clean_norm = clean_no_space.replace(",", "")
    elif "." in clean_no_space:
        parts = clean_no_space.split(".")
        if len(parts) == 2 and len(parts[1]) == 3 and len(parts[0]) <= 3:
            # Likely thousands separator: e.g. 5.000 -> 5000 in VND
            if default_currency == "VND":
                clean_norm = clean_no_space.replace(".", "")
                warnings.append("Interpreted single dot as thousands separator for VND.")
            else:
                clean_norm = clean_no_space
        else:
            clean_norm = clean_no_space
    else:
        clean_norm = clean_no_space

    try:
        val = Decimal(clean_norm)
        return val, "valid", warnings
    except InvalidOperation:
        return None, "invalid", [f"Unable to parse Decimal from '{raw_amount}'"]


def parse_date(raw_date: Optional[str]) -> Tuple[Optional[str], str, List[str]]:
    """Parse date strings into ISO format YYYY-MM-DD."""
    if not raw_date:
        return None, "empty", []

    clean = raw_date.strip()

    # Matches DD/MM/YYYY or DD-MM-YYYY or DD.MM.YYYY
    m1 = re.search(r"\b(\d{1,2})[\/\-\.](\d{1,2})[\/\-\.](\d{4})\b", clean)
    if m1:
        day, month, year = int(m1.group(1)), int(m1.group(2)), int(m1.group(3))
        if 1 <= day <= 31 and 1 <= month <= 12:
            return f"{year:04d}-{month:02d}-{day:02d}", "valid", []

    # Matches YYYY-MM-DD
    m2 = re.search(r"\b(\d{4})[\/\-\.](\d{1,2})[\/\-\.](\d{1,2})\b", clean)
    if m2:
        year, month, day = int(m2.group(1)), int(m2.group(2)), int(m2.group(3))
        if 1 <= day <= 31 and 1 <= month <= 12:
            return f"{year:04d}-{month:02d}-{day:02d}", "valid", []

    # Vietnamese natural language date, including bilingual form labels.
    m3 = re.search(
        r"(?:ngày\s*(?:\(date\)\s*)?)?(\d{1,2})\s*tháng\s*"
        r"(?:\(month\)\s*)?(\d{1,2})\s*năm\s*(?:\(year\)\s*)?(\d{4})",
        clean,
        re.IGNORECASE,
    )
    if m3:
        day, month, year = int(m3.group(1)), int(m3.group(2)), int(m3.group(3))
        if 1 <= day <= 31 and 1 <= month <= 12:
            return f"{year:04d}-{month:02d}-{day:02d}", "valid", []

    return None, "invalid_format", [f"Could not parse valid date from '{raw_date}'"]


def normalize_container_number(
    raw_cont: Optional[str],
) -> Tuple[Optional[str], str, List[str]]:
    """Normalize container number (ISO 6346: 4 letters + 7 digits, e.g. TCNU1234567)."""
    if not raw_cont:
        return None, "empty", []

    clean = re.sub(r"[^\w]", "", raw_cont.upper().strip())
    warnings: List[str] = []

    if re.match(r"^[A-Z]{4}\d{7}$", clean):
        return clean, "valid", warnings

    warnings.append(f"Container number '{raw_cont}' does not follow ISO 6346 format.")
    return clean, "warning", warnings
