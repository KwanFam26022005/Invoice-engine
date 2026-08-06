"""Parser registry for instantiating and discovering document parsers."""

from typing import Dict, List, Type
from document_engine.core.exceptions import ParserNotFoundError
from document_engine.parsers.base import DocumentParser
from document_engine.parsers.docling_native import DoclingNativeParser
from document_engine.parsers.docling_ocr import DoclingOCRParser
from document_engine.parsers.paddleocr_vl import PaddleOCRVLParser
from document_engine.parsers.pymupdf_native import PyMuPDFNativeParser


class ParserRegistry:
    def __init__(self):
        self._parsers: Dict[str, Type[DocumentParser]] = {}
        self.register("pymupdf_native", PyMuPDFNativeParser)
        self.register("docling_native", DoclingNativeParser)
        self.register("docling_ocr", DoclingOCRParser)
        self.register("paddleocr_vl", PaddleOCRVLParser)

    def register(self, parser_id: str, parser_cls: Type[DocumentParser]) -> None:
        self._parsers[parser_id] = parser_cls

    def get_parser(self, parser_id: str) -> DocumentParser:
        if parser_id not in self._parsers:
            raise ParserNotFoundError(f"Parser '{parser_id}' is not registered.")
        return self._parsers[parser_id]()

    def list_parsers(self) -> List[str]:
        return list(self._parsers.keys())


default_registry = ParserRegistry()
