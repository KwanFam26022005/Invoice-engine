"""Parser registry for instantiating and discovering document parsers."""

from pathlib import Path
from typing import Any, Dict, List, Optional, Type

from document_engine.config.parser_config import (
    apply_env_overrides,
    load_parser_config,
    merge_parser_config,
)
from document_engine.core.exceptions import ParserNotFoundError
from document_engine.parsers.base import DocumentParser
from document_engine.parsers.docling_native import (
    DoclingNativeParser,
    _DOCLING_NATIVE_DEFAULT_CONFIG,
)
from document_engine.parsers.docling_ocr import (
    DoclingOCRParser,
    _DOCLING_OCR_DEFAULT_CONFIG,
)
from document_engine.parsers.paddleocr_vl import (
    PaddleOCRVLParser,
    _PADDLE_DEFAULT_CONFIG,
)
from document_engine.parsers.pymupdf_native import PyMuPDFNativeParser


# Maps parser_id -> built-in default config
_PARSER_DEFAULTS: Dict[str, Dict[str, Any]] = {
    "pymupdf_native": {},
    "docling_native": dict(_DOCLING_NATIVE_DEFAULT_CONFIG),
    "docling_ocr": dict(_DOCLING_OCR_DEFAULT_CONFIG),
    "paddleocr_vl": dict(_PADDLE_DEFAULT_CONFIG),
}


class ParserRegistry:
    def __init__(self):
        self._parsers: Dict[str, Type[DocumentParser]] = {}
        self.register("pymupdf_native", PyMuPDFNativeParser)
        self.register("docling_native", DoclingNativeParser)
        self.register("docling_ocr", DoclingOCRParser)
        self.register("paddleocr_vl", PaddleOCRVLParser)

    def register(self, parser_id: str, parser_cls: Type[DocumentParser]) -> None:
        self._parsers[parser_id] = parser_cls

    def get_parser(
        self,
        parser_id: str,
        config_dir: Optional[Path] = None,
    ) -> DocumentParser:
        if parser_id not in self._parsers:
            raise ParserNotFoundError(f"Parser '{parser_id}' is not registered.")

        # Load config with precedence: defaults < YAML < env
        defaults = _PARSER_DEFAULTS.get(parser_id, {})
        loaded = load_parser_config(parser_id, config_dir=config_dir)
        env_overrides = apply_env_overrides(parser_id, {})
        merged = merge_parser_config(defaults, loaded, env_overrides)

        parser_cls = self._parsers[parser_id]
        return parser_cls(config=merged)

    def list_parsers(self) -> List[str]:
        return list(self._parsers.keys())


default_registry = ParserRegistry()
