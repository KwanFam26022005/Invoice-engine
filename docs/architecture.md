# System Architecture - Universal Invoice & Business Document Engine

## Overview
The Universal Invoice & Business Document Engine is a local-first, privacy-respecting document processing pipeline designed to handle native and scanned Vietnamese business documents.

## Two-Level Processing Model

```
Level 1: Document Parsing
PDF Document ──> Inspector ──> Parser Router ──> Isolated Worker (PyMuPDF / Docling / PaddleOCR-VL) ──> DocumentIR

Level 2: Business Interpretation
DocumentIR ──> Document Classifier ──> Specialized Family Mapper ──> Canonical Payload + Field Evidence ──> Business Validator ──> DuckDB Storage V2
```

### Component Isolation
1. **Base Process**: Standard Python environment containing lightweight libraries (`PyMuPDF`, `Pydantic`, `DuckDB`, `PyYAML`).
2. **Heavy Runtimes**: Subprocess workers (`.venv-docling`, `.venv-paddlevl`) executing heavy layout models via machine-readable JSON IPC over standard stdin/stdout.
