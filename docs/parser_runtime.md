# Parser Runtime & Worker Isolation

## Isolation Architecture
Heavy document layout engines (Docling and PaddleOCR-VL) are decoupled from the base application process to eliminate library version conflicts (PyTorch, Paddle, Docling, C++ bindings).

```
document-engine (base venv)
       │
       ├── PyMuPDF Native (in-process)
       │
       ├── Docling Worker (JSON-IPC via subprocess)
       │     └─ .venv-docling\Scripts\python.exe
       │
       └── PaddleOCR-VL Worker (JSON-IPC via subprocess)
             └─ .venv-paddlevl\Scripts\python.exe
```

## Supported Parsers
- `pymupdf_native`: Fast native vector text layer extraction.
- `docling_native`: Structure & table parser for vector PDFs.
- `docling_ocr`: Scanned PDF OCR parser using EasyOCR (vi/en).
- `paddleocr_vl`: Official PaddleOCR-VL v1.6 pipeline fallback parser for complex, irregular layout documents.

## Offline Model Policy
- Processing runtime operates 100% offline.
- Automatic model downloading at runtime is disabled unless `ALLOW_MODEL_DOWNLOAD=1` is explicitly specified during setup.
