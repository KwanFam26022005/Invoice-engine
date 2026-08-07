"""Inspect the dedicated Docling semantic environment without running inference."""

import importlib
import importlib.util
import json
import sys


required = {
    "docling": "docling",
    "document_extractor": "docling.document_extractor",
    "pipeline_options": "docling.datamodel.pipeline_options",
    "extraction_pipeline": "docling.pipeline.extraction_vlm_pipeline",
    "torch": "torch",
    "transformers": "transformers",
}

status = {name: importlib.util.find_spec(module) is not None for name, module in required.items()}
versions = {"python": sys.version.split()[0]}
for package in ("docling", "torch", "transformers", "pydantic"):
    try:
        mod = importlib.import_module(package)
        versions[package] = getattr(mod, "__version__", "installed")
    except Exception:
        pass

api_symbols = {}
if status["docling"]:
    try:
        from docling.document_extractor import DocumentExtractor, ExtractionFormatOption
        from docling.datamodel.pipeline_options import VlmExtractionPipelineOptions

        api_symbols = {
            "DocumentExtractor": DocumentExtractor is not None,
            "ExtractionFormatOption": ExtractionFormatOption is not None,
            "VlmExtractionPipelineOptions": VlmExtractionPipelineOptions is not None,
        }
    except Exception as exc:
        api_symbols = {"error_type": type(exc).__name__}

print(json.dumps({"modules": status, "versions": versions, "api_symbols": api_symbols}, indent=2))
