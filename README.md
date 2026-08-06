# Invoice Engine Benchmark

Local-first benchmark for document extraction engines on Vietnamese invoices and internal PDF forms. The project measures extraction quality, latency, CPU/RAM/GPU usage, stability, validation outcomes, and batch-level financial aggregation.

## Architecture

```text
PDF input
  → input-profile inspection (native text or image-only scan)
  → DocumentEngine registry
  → isolated warm/cold worker
  → raw engine output and runtime identity
  → canonical normalization
  → business validation
  → evaluation and cross-engine comparison
  → DuckDB aggregation
  → Excel/CSV report
```

## Benchmark tracks

Engines are compared only within compatible input tracks:

| Track | Input | Baseline profiles |
|---|---|---|
| `native_pdf` | PDF with a usable embedded text layer | `docling_text_only_cpu`, `docling_table_cpu` |
| `scan_ocr` | Image-only/scanned PDF | `docling_ocr_easyocr_vi_cpu`, `ppstructure_v3_vi_table_cpu` |

An incompatible engine/document pairing is recorded as `SKIPPED` before model loading. This prevents an OCR-disabled parser from being ranked against OCR-enabled pipelines on scanned PDFs.

## Engine status

- **Docling native profiles:** implemented.
- **Docling EasyOCR Vietnamese profile:** implemented for scanned PDFs.
- **PP-StructureV3:** implemented with the PaddleOCR 3.x `PPStructureV3` pipeline API.
- **PP-StructureV2 legacy:** retained under an explicit, disabled legacy profile; it is never labelled as V3.
- **PaddleOCR-VL and Sparrow:** planned optional adapters, not production-ready in the current repository.

Every real-engine result records the concrete runtime class and installed package versions in `raw_payload.runtime_metadata`.

## Base installation

```powershell
git clone https://github.com/KwanFam26022005/Invoice-engine.git
cd Invoice-engine
python -m pip install -e ".[dev]"
```

## Optional engine environments

Keep heavyweight engines in separate virtual environments when dependencies conflict.

### Docling native parsing

```powershell
python -m pip install -e ".[docling,dev]"
```

### Docling OCR

```powershell
python -m pip install -e ".[docling_ocr,dev]"
```

### PP-StructureV3

PaddleOCR 3.x requires PaddlePaddle 3.x. Install the appropriate CPU or GPU PaddlePaddle wheel for the target machine first, then:

```powershell
python -m pip install -e ".[paddle,dev]"
```

### PP-StructureV2 legacy

The legacy dependency group is intentionally separate and the profile is disabled by default:

```powershell
python -m pip install -e ".[paddle_legacy,dev]"
```

Do not install the V2 and V3 Paddle stacks into the same benchmark environment.

## Dataset preparation

```powershell
python scripts\prepare_benchmark_dataset.py `
  --dataset-root "D:\Documents-engine\datasets"
```

Read-only integrity verification:

```powershell
python scripts\prepare_benchmark_dataset.py `
  --dataset-root "D:\Documents-engine\datasets" `
  --verify-only
```

The current local corpus contains 51 valid image-only PDFs. Raw PDFs, images, ZIP archives, OCR output, and generated benchmark runs are excluded from Git.

## Tests

Base suite:

```powershell
python -m ruff check src tests scripts
python -m compileall -q src tests scripts
python -m pytest -v
```

Heavy model extraction tests are explicit opt-in tests:

```powershell
$env:RUN_OPTIONAL_ENGINE_TESTS = "1"
python -m pytest -m optional_engine -v
```

Without that environment variable, optional model tests report `SKIPPED`; health checks and adapter contract tests still run without downloading model weights.

## Example benchmark commands

Scanned PDF track:

```powershell
python -m document_benchmark.cli `
  --pdfs "D:\Documents-engine\datasets\benchmark\documents\utilities\sample.pdf" `
  --engines docling_ocr_easyocr_vi_cpu ppstructure_v3_vi_table_cpu `
  --warmup-runs 1 `
  --measured-runs 3 `
  --timeout 300
```

Native-text track:

```powershell
python -m document_benchmark.cli `
  --pdfs "D:\path\to\native_text_invoice.pdf" `
  --engines docling_text_only_cpu docling_table_cpu
```

## Security policy

The application is local-only for this scope. It does not send documents to cloud APIs. Never commit invoice PDFs, document images, ZIP archives, model caches, extracted full text, or generated run artifacts.
