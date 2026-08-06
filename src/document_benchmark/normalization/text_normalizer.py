"""Text normalizer ensuring Unicode NFC normalization and whitespace collapse."""

import re
import unicodedata


def normalize_text(text: str) -> str:
    """Normalize text into Unicode NFC form while collapsing extra spaces."""
    if not text:
        return ""
    # NFC normalization
    normalized = unicodedata.normalize("NFC", str(text))
    # Replace tabs, newlines inside inline string, collapse multiple spaces
    normalized = re.sub(r"[ \t]+", " ", normalized).strip()
    return normalized
