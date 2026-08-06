"""Normalization package."""

from document_benchmark.normalization.canonical_normalizer import CanonicalNormalizer
from document_benchmark.normalization.date_normalizer import normalize_date
from document_benchmark.normalization.field_mapper import detect_document_family
from document_benchmark.normalization.number_normalizer import normalize_number
from document_benchmark.normalization.tax_id_normalizer import normalize_tax_id
from document_benchmark.normalization.text_normalizer import normalize_text

__all__ = [
    "CanonicalNormalizer",
    "detect_document_family",
    "normalize_date",
    "normalize_number",
    "normalize_tax_id",
    "normalize_text",
]
