"""Parsers package exports."""

from document_engine.parsers.base import DocumentParser, ParserHealth, ParserSpec
from document_engine.parsers.docling_native import DoclingNativeParser
from document_engine.parsers.docling_ocr import DoclingOCRParser
from document_engine.parsers.paddleocr_vl import PaddleOCRVLParser
from document_engine.parsers.pymupdf_native import PyMuPDFNativeParser
from document_engine.parsers.registry import ParserRegistry, default_registry

__all__ = [
    "DocumentParser",
    "ParserSpec",
    "ParserHealth",
    "PyMuPDFNativeParser",
    "DoclingNativeParser",
    "DoclingOCRParser",
    "PaddleOCRVLParser",
    "ParserRegistry",
    "default_registry",
]
