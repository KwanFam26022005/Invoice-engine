# Phase 9D — Docling Semantic Extraction Canary

Phase 9D adds a local-only, schema-conditioned Docling extraction path. It is a canary and is not wired into the production `DocumentPipeline` yet.

The adapter returns `SemanticExtractionResult` only. It never writes directly to `BusinessDocumentEnvelope`; downstream evidence grounding and deterministic validation remain mandatory.

## Runtime boundary

The heavy VLM stack is isolated in `.venv-docling-semantic` and addressed through worker ID `docling_semantic`. The base process must not import Docling VLM dependencies.

The current Docling API is probed at runtime before extraction. Required symbols include `DocumentExtractor`, `ExtractionFormatOption`, `VlmExtractionPipelineOptions`, and `ExtractionVlmPipeline`.

Runtime is offline by default. `HF_HUB_OFFLINE=1` and `TRANSFORMERS_OFFLINE=1` are set when model download is not explicitly allowed. `DOCLING_SEMANTIC_ARTIFACTS_PATH` must point at locally prepared model assets for normal execution.

The setup script installs dependencies only; it does not download model weights.

## Model preparation

Model download is an explicit online preparation step, separate from runtime:

```powershell
.\scripts\prepare_docling_semantic_model.ps1
```

The default preparation target is `workspace/model_cache/docling_semantic`, and the default model repository is `numind/NuExtract-2.0-2B`.

After preparation, verify the cache without loading inference:

```powershell
$env:DOCLING_SEMANTIC_ARTIFACTS_PATH = (Resolve-Path workspace\model_cache\docling_semantic).Path
.venv-docling-semantic\Scripts\python.exe scripts\check_docling_semantic_model_cache.py
```

No model weights or caches may be committed.

## CPU-safe runtime

`VlmExtractionPipelineOptions` defaults to NuExtract-2B. The worker now makes the accelerator choice explicit and keeps runtime local.

- `DOCLING_SEMANTIC_DEVICE=auto` selects CUDA only when available; otherwise CPU.
- `DOCLING_SEMANTIC_DEVICE=cpu` forces CPU.
- Runtime 8-bit loading is disabled on CPU because the Docling/Hugging Face option requires CUDA-backed quantization.
- `DOCLING_SEMANTIC_LOAD_IN_8BIT` only has effect on CUDA.
- `DOCLING_SEMANTIC_NUM_THREADS` can cap CPU inference threads.
- `DOCLING_SEMANTIC_TORCH_DTYPE` can override the default `bfloat16` when a canary requires a compatibility experiment.

The worker records requested/actual device, cache readiness, quantization state, model repository, and model revision in privacy-safe health metadata.

## Initial schemas

Only these families are registered in Phase 9D:

- `sales_invoice`
- `utility_consumption_invoice`
- `tax_withholding_certificate`

Templates mirror canonical field paths but do not contain private examples or vendor-specific literals.

Nested output is flattened into atomic paths such as `common.grand_total` and `line_items[0].quantity`. Null scalar outputs become abstentions rather than fabricated values.

## Safety rules

- No cloud API or remote document service.
- No private values in templates or logs.
- No raw model response text is persisted by the worker.
- No model output becomes financial truth automatically.
- Candidate evidence hints are page-only hints until `EvidenceGrounder` proves the value exists in `DocumentIR`.
- Heavy inference remains optional and must not run during the default test suite.

## Local verification sequence

1. Run `scripts/setup_docling_semantic_env.ps1` once for dependency setup.
2. Run `.venv-docling-semantic\Scripts\python.exe scripts\check_docling_semantic_env.py` to inspect the installed API without inference.
3. Run `.\scripts\prepare_docling_semantic_model.ps1` as the explicit online model preparation step.
4. Set `DOCLING_SEMANTIC_ARTIFACTS_PATH` in the shell that will run the canary.
5. Run `.venv-docling-semantic\Scripts\python.exe scripts\check_docling_semantic_model_cache.py`.
6. Run the worker healthcheck and only then execute the synthetic semantic canary.
7. The optional canary must produce semantic candidates and ground at least one candidate back to synthetic `DocumentIR` evidence.

A real model canary is not considered verified until actual local inference has been run successfully. Phase 9E must not start while Phase 9D real inference is still unverified.
