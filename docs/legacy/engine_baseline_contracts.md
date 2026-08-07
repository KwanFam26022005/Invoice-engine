# Engine Baseline Contracts

This document defines the minimum truthfulness and comparability requirements for real document-engine benchmarks.

## 1. Engine identity

A benchmark result must identify:

- `engine_id` and `config_id`;
- adapter class;
- concrete runtime class and module;
- installed package versions;
- engine generation, such as `PP-StructureV3` or `PP-StructureV2 legacy`;
- benchmark track;
- OCR enabled/disabled state when applicable.

These values are stored in `raw_payload.runtime_metadata`.

## 2. Benchmark tracks

### Native PDF

`native_pdf` is for documents with a usable embedded text layer. OCR-disabled Docling profiles belong to this track.

### Scanned PDF

`scan_ocr` is for image-only or scanned PDFs. Docling OCR and PP-StructureV3 belong to this track.

The controller checks the document metadata and engine capabilities before worker startup. Known-incompatible pairings are recorded as `SKIPPED`; they are excluded from measured success/failure counts and accuracy comparison.

## 3. PP-Structure version contract

`ppstructure_v3` must instantiate the public `paddleocr.PPStructureV3` class and call `predict(input=...)`. The adapter preserves each page's `json` and `markdown` attributes.

The old `paddleocr.PPStructure` API is retained only as `ppstructure_v2_legacy`. Its configuration is disabled by default and requires a separate PaddleOCR 2.x environment.

## 4. Docling OCR contract

The scanned-PDF Docling profile uses:

- `do_ocr=true`;
- EasyOCR;
- Vietnamese and English language codes;
- CPU execution by default;
- table structure extraction enabled.

OCR-disabled profiles declare `supports_scanned_pdf=false` and cannot run against image-only documents through the benchmark controller.

## 5. Health-check contract

`healthcheck()` may import lightweight package modules and inspect public symbols, but it must not:

- instantiate a model pipeline;
- download model weights;
- process a document;
- allocate large GPU/CPU model state.

Heavy preparation remains in `prepare()`.

## 6. Optional-engine test contract

Base tests never require downloading model weights. Real model extraction tests require:

```powershell
$env:RUN_OPTIONAL_ENGINE_TESTS = "1"
python -m pytest -m optional_engine -v
```

When the environment variable is absent, those tests must report `SKIPPED`, not silently return as passed.

## 7. Acceptance criteria for this phase

- PaddleOCR V2 cannot be reported as V3.
- A real V3 adapter uses the official V3 class and output properties.
- Scanned PDFs cannot be benchmarked with OCR-disabled Docling profiles.
- Native and scanned tracks remain separated.
- Runtime package versions and concrete classes are preserved.
- Optional model tests are explicit and use generated, non-sensitive fixtures.
