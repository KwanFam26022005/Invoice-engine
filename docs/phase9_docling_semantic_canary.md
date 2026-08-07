# Phase 9D — Docling Semantic Extraction Canary

Phase 9D adds a local-only, schema-conditioned Docling extraction path. It is a canary and is not wired into the production `DocumentPipeline` yet.

The adapter returns `SemanticExtractionResult` only. It never writes directly to `BusinessDocumentEnvelope`; downstream evidence grounding and deterministic validation remain mandatory.

## Runtime boundary

The heavy VLM stack is isolated in `.venv-docling-semantic` and addressed through worker ID `docling_semantic`. The base process must not import Docling VLM dependencies.

The current Docling API is probed at runtime before extraction. Required symbols include `DocumentExtractor`, `ExtractionFormatOption`, `VlmExtractionPipelineOptions`, and `ExtractionVlmPipeline`.

Runtime is offline by default. `HF_HUB_OFFLINE=1` and `TRANSFORMERS_OFFLINE=1` are set when model download is not explicitly allowed. `DOCLING_SEMANTIC_ARTIFACTS_PATH` must point at locally prepared model assets for normal execution.

The setup script installs dependencies only; it does not download model weights.

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
3. Prepare model artifacts explicitly and set `DOCLING_SEMANTIC_ARTIFACTS_PATH`.
4. Run the worker healthcheck and only then execute a synthetic semantic canary.

A real model canary is not considered verified until actual local inference has been run successfully.
