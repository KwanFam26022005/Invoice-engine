# Phase 9E — PaddleOCR-VL Visual/Layout Canary

Phase 9E introduces a controlled local PaddleOCR-VL visual/layout canary. It is not a replacement for Phase 9D schema-conditioned semantic extraction and it is not wired into production task routing yet.

## Scope

The purpose of Phase 9E is to answer a narrower question:

> When the existing `DocumentIR` is spatially inadequate (for example, missing table structure or important layout relationships), can a local PaddleOCR-VL pass recover useful blocks, reading order, table structure, and geometry with explicit provenance?

This phase therefore produces `DocumentIR`, not canonical business truth and not a `SemanticExtractionResult`.

The intended later comparison in Phase 9F is between independent paths, for example:

1. frozen deterministic mapper on the normal parser route;
2. Docling semantic extraction from the existing IR;
3. PaddleOCR-VL visual IR followed by the same downstream family/evidence rules;
4. a hybrid policy only after the independent paths have been measured.

## Current public API alignment

The Phase 9E worker is aligned with the current PaddleOCR-VL direct-inference interface:

- pipeline version `v1.6`;
- local `vl_rec_backend="native"`;
- `layout_detection_model_dir` and `vl_rec_model_dir` for explicit local artifacts;
- `predict_iter(...)` when available, with `predict(...)` as a compatibility fallback;
- no legacy `use_gpu`, `use_angle_cls`, `use_doc_unwarp`, or repository `engine` argument;
- `use_queues=False` for the single-document controlled canary.

The installed local environment remains the source of truth. Before any real inference, run:

```powershell
.venv-paddlevl\Scripts\python.exe scripts\check_paddleocr_vl_env.py
```

The checker inspects symbols/signatures only. It does not load model weights.

## Operator API inspection evidence — 2026-08-10

The operator inspected both local Paddle environments without running inference or loading weights.

Preferred isolated worker environment:

```text
.venv-paddlevl
Python 3.10.11
paddle 3.2.1
paddleocr 3.7.0
pydantic 2.13.4
PaddleOCRVL: available
predict: available
predict_iter: available
```

A secondary `.venv-paddle3` environment also exposed the same PaddleOCRVL API surface, but used Paddle 3.2.0. Phase 9E keeps `.venv-paddlevl` as the canonical worker environment because the repository setup contract requires `paddlepaddle>=3.2.1`.

The locally inspected constructor exposes `pipeline_version`, `layout_detection_model_name`, `layout_detection_model_dir`, `vl_rec_model_name`, `vl_rec_model_dir`, `vl_rec_backend`, `use_queues`, and the expected visual preprocessing toggles. The locally inspected `predict` and `predict_iter` methods expose the expected inference controls. Therefore the API-inspection gate is satisfied.

No inference was executed and no model was loaded during this inspection.

## Offline runtime boundary

Normal Phase 9E inference requires both explicit local model directories:

```powershell
$env:PADDLE_LAYOUT_MODEL_DIR = "<local-layout-model-dir>"
$env:PADDLE_VL_REC_MODEL_DIR = "<local-vl-rec-model-dir>"
```

Both directories must contain recognized model weights. A generic `.paddleocr`/`.paddlex` cache is treated only as partially verified because it does not prove the exact two models required by the canary.

Runtime uses only the native/local VL backend. Server backends are rejected in Phase 9E.

Model preparation/download must remain a separate explicit step. The default test suite must never download or load PaddleOCR-VL models.

## DocumentIR correctness fixes

Phase 9E hardens the pre-existing Paddle worker before any real canary:

- `SourceDocument` now uses the canonical `filename` and `sha256` fields;
- parser requests propagate `source_sha256`;
- Paddle block labels are stored as `BlockIR.block_type`;
- block, table, and cell bounding boxes are converted to `Geometry` rather than being silently dropped as unknown `bbox` fields;
- page width/height and reading order are preserved;
- parser provenance does not persist host-specific model-directory paths.

The geometry coordinate system is recorded as `image_pixels_topleft` because PaddleOCR-VL layout results are image-space coordinates, not PDF-point coordinates.

## Optional synthetic canary

The real canary is intentionally opt-in and the filename does not match default pytest discovery:

```text
tests/e2e/optional_paddleocr_vl_canary.py
```

It creates a synthetic one-page invoice containing:

- an invoice heading;
- a document number;
- a grand total;
- a small two-column visual table.

Success requires:

- the isolated Paddle worker is healthy;
- real local PaddleOCR-VL inference executes;
- one `DocumentIR` page is produced;
- at least one visual block is produced;
- at least one block/table preserves geometry.

Table recognition itself is measured but is not a hard pass criterion for this first canary, because the primary gate is proving the local visual/layout path and its provenance/geometry contract.

No private corpus is used.

## Verification order

1. Sync the Phase 9 branch and run the normal lightweight/full code gates.
2. Inspect `.venv-paddlevl` with `scripts/check_paddleocr_vl_env.py`.
3. Confirm exact installed `PaddleOCRVL` signatures before model preparation.
4. Obtain the installed PaddleX pipeline configuration and confirm the exact default layout/VL model names.
5. Prepare the required layout and VL-recognition model artifacts explicitly.
6. Configure `PADDLE_LAYOUT_MODEL_DIR` and `PADDLE_VL_REC_MODEL_DIR`.
7. Run a worker healthcheck with downloads disabled.
8. Run the optional synthetic visual canary once.
9. Record runtime, block count, table count, geometry count, and provenance.
10. Stop. Do not tune against the private corpus in Phase 9E.

## Status

The API-inspection gate is complete. Phase 9E remains unverified until local model artifacts are prepared and a real synthetic visual inference succeeds.

Allowed status labels:

- `PHASE_9E_API_VERIFIED_MODEL_PREP_PENDING`
- `PHASE_9E_MODEL_CACHE_NOT_READY`
- `PHASE_9E_RUNTIME_BLOCKED`
- `PHASE_9E_VISUAL_CANARY_PARTIAL`
- `PHASE_9E_VISUAL_CANARY_VERIFIED`
