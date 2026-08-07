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

## Parser Configuration System

### Config Files
Each parser can have a YAML config file at `configs/parsers/<parser_id>.yaml`. These files are loaded automatically by `ParserRegistry.get_parser()`.

### Config Precedence
```
built-in safe defaults (in parser class)
        ↓
configs/parsers/<parser_id>.yaml  (config: sub-key)
        ↓
environment variable overrides
```

Higher-precedence values override lower ones. YAML `null` values do **not** override built-in defaults; only explicitly set values do.

### Environment Variables

| Variable | Parser | Config Key |
|---|---|---|
| `DOCUMENT_ENGINE_PARSER_CONFIG_DIR` | all | Overrides default config directory |
| `PADDLE_LAYOUT_MODEL_DIR` | `paddleocr_vl` | `layout_detection_model_dir` |
| `PADDLE_VL_REC_MODEL_DIR` | `paddleocr_vl` | `vl_rec_model_dir` |
| `ALLOW_MODEL_DOWNLOAD` | `paddleocr_vl` | Permits runtime model download when `=1` |

### Identity Validation
The `parser_id` field in YAML must match the requested parser ID. Mismatched YAML files are rejected with a `ValueError`, never silently loaded.

## Offline Model Policy
- Processing runtime operates 100% offline.
- Automatic model downloading at runtime is disabled unless `ALLOW_MODEL_DOWNLOAD=1` is explicitly specified during setup.

### Model Directory Configuration

PaddleOCR-VL requires pre-downloaded model weights. Configure local model directories to enable fully offline operation:

**Windows PowerShell Setup:**
```powershell
$env:PADDLE_LAYOUT_MODEL_DIR = "D:\models\paddle\layout"
$env:PADDLE_VL_REC_MODEL_DIR = "D:\models\paddle\vl-rec"
```

**Linux/macOS Setup:**
```bash
export PADDLE_LAYOUT_MODEL_DIR="/opt/models/paddle/layout"
export PADDLE_VL_REC_MODEL_DIR="/opt/models/paddle/vl-rec"
```

### Model Cache Readiness States

| Status | `model_cache_ready` | Meaning |
|---|---|---|
| `READY_LOCAL_MODEL_DIRS` | `True` | Both explicit model dirs exist and contain recognized model artifacts |
| `LOCAL_MODEL_DIRS_PARTIALLY_VERIFIED` | `False` | Dirs exist but lack recognized model artifacts |
| `LOCAL_MODEL_DIRS_INVALID` | `False` | One or both dirs missing, not directories, or incomplete |
| `MODEL_CACHE_PARTIALLY_VERIFIED` | `False` | Default cache has some files but is not verified |
| `CACHE_MISSING` | `False` | No cache found |

### Runtime Rule
```
ALLOW_MODEL_DOWNLOAD=0  +  explicit valid model dirs  =  offline Paddle worker allowed
ALLOW_MODEL_DOWNLOAD=0  +  no valid model dirs         =  Paddle worker blocked
ALLOW_MODEL_DOWNLOAD=1                                  =  Paddle worker allowed (may download)
```

> **Important:** Do not commit machine-specific absolute paths to `configs/parsers/paddleocr_vl.yaml`. Use environment variables for local model directories.
