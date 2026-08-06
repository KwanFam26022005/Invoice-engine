# Reproducible Smoke Benchmark Guide

This phase validates engine integration and operational behavior on the ordered 10-document `smoke_test.txt` split. It does **not** rank extraction accuracy because the current documents have ground-truth level 0.

## Outputs

A campaign is stored under:

```text
runs/smoke/<campaign_id>/
├── campaign.json
├── preflight/
├── engine_runs/
└── reports/
    ├── campaign_summary.json
    ├── document_runs.csv
    ├── engine_summary.csv
    ├── correctness_index.csv
    ├── blockers.json
    └── smoke_report.md
```

The campaign fingerprint includes the ordered document IDs, SHA-256 values, filenames, page counts, and input profiles. Reusing a campaign ID with a changed split or changed document bytes is rejected.

## Correctness and performance separation

For each engine/document pair, the first successful measured repeat is indexed in `correctness_index.csv`. Remaining repeats are retained only as latency, resource, and stability samples. Accuracy metrics remain `NOT_COMPUTED_NO_GROUND_TRUTH` until reviewed Level-1 or Level-2 ground truth exists.

## Docling OCR run

Use the environment where Docling 2.x and EasyOCR are already installed:

```powershell
cd D:\Documents-engine

document-smoke-benchmark `
  --dataset-root "D:\Documents-engine\datasets" `
  --engines docling_ocr_easyocr_vi_cpu `
  --campaign-id "smoke_scan_baseline_001" `
  --warmup-runs 1 `
  --measured-runs 3 `
  --timeout 600
```

## Create the dedicated PP-StructureV3 environment

The official PaddleOCR documentation assigns PP-StructureV3 to the `doc-parser` dependency group. PaddleOCR 3.x requires an inference engine; this project uses PaddlePaddle CPU in a separate Windows virtual environment.

```powershell
cd D:\Documents-engine

powershell -ExecutionPolicy Bypass -File .\scripts\setup_paddle3_env.ps1
```

The setup script:

1. creates `.venv-paddle3`;
2. installs PaddlePaddle CPU 3.2.0 from the official stable index;
3. installs `paddleocr[doc-parser]>=3,<4`;
4. installs this project with development dependencies;
5. checks major versions and the public `PPStructureV3` symbol;
6. does not instantiate the pipeline or download model weights.

Official references:

- PaddleOCR installation: https://www.paddleocr.ai/main/en/version3.x/installation.html
- PaddlePaddle installation: https://www.paddleocr.ai/main/en/version3.x/paddlepaddle_installation.html
- PP-StructureV3 usage: https://www.paddleocr.ai/latest/en/version3.x/pipeline_usage/PP-StructureV3.html

## PP-StructureV3 run

Use the same campaign ID so the report combines both environments while enforcing the same dataset fingerprint:

```powershell
cd D:\Documents-engine

.\.venv-paddle3\Scripts\python.exe -m document_benchmark.smoke.runner `
  --dataset-root "D:\Documents-engine\datasets" `
  --engines ppstructure_v3_vi_table_cpu `
  --campaign-id "smoke_scan_baseline_001" `
  --warmup-runs 1 `
  --measured-runs 3 `
  --timeout 900
```

The first PP-StructureV3 run may download model weights. Record that as cold preparation overhead; do not interpret it as warm inference latency.

## Preflight only

```powershell
document-smoke-benchmark `
  --dataset-root "D:\Documents-engine\datasets" `
  --engines docling_ocr_easyocr_vi_cpu `
  --campaign-id "smoke_scan_baseline_001" `
  --preflight-only
```

A preflight checks package and adapter identity without calling `prepare()`.

## Regenerate reports

```powershell
document-smoke-benchmark `
  --dataset-root "D:\Documents-engine\datasets" `
  --campaign-id "smoke_scan_baseline_001" `
  --report-only
```

## Acceptance boundary

The smoke phase may report:

- availability and blockers;
- successful/failed/skipped executions;
- latency mean, p50, p95, and maximum;
- peak CPU/RAM/GPU fields where available;
- output text length, page count, and table count;
- concrete runtime class and package versions.

It must not claim field accuracy, line-item F1, financial aggregation accuracy, or a winning engine without reviewed ground truth.
