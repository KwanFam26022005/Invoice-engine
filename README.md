# Universal Invoice and Business Document Engine

A local-first enterprise document intake, inspection, parser routing, deterministic validation, DuckDB persistence, and human review system designed for complex Vietnamese business documents (invoices, utility statements, port services, tax withholding certificates, receipts, and supporting statements).

## Features

- **Local-First & Privacy Preserving**: 100% offline processing mode. Document data never leaves the local machine. Optional model prefetching requires explicit `ALLOW_MODEL_DOWNLOAD=1` opt-in.
- **Isolated Worker Runtime Architecture**: Heavy parser runtimes (`Docling Native`, `Docling OCR`, and `PaddleOCR-VL`) run in dedicated isolated subprocess virtual environments via machine-readable JSON IPC, preventing base environment dependency bloat.
- **Evidence-Grade Document IR**: Page-aware structured representation preserving exact page dimensions, text blocks, reading order, cell layout, bounding boxes, and parser provenance.
- **Disambiguated Schema Model**: Missing or unextracted fields remain `Optional[Decimal] = None` to cleanly distinguish absent fields from valid `Decimal("0")` zero amounts.
- **Specialized Evidence Mappers**: Dedicated family mappers (`sales_invoice`, `utility_consumption_invoice`, `tax_withholding_certificate`) linking extracted values directly to backing `EvidenceReference` blocks and table cells.
- **Hardened Router & Structural Quality Gate**: Removes silent parser substitution and length-based heuristics. Dispatches via `ParseQualityReport` and semantic completeness scores.
- **Two-Level Execution & Semantic Fallback Loop**: Automatically triggers fallback parsing when primary parsing is incomplete or fails critical validation rules.
- **DuckDB Storage V2**: Persists relational projections, evidence references, completeness scores, quality reports, and canonical payloads in isolated document transactions.
- **Private Real-Document Pilot Workflow**: Process private real-world local document samples using pilot manifests without committing confidential data to Git.

---

## Workspace Directory Structure

All runtime artifacts are written to `DOCUMENT_ENGINE_HOME` (default: `D:\Documents-engine\workspace`):

```text
workspace/
├── inbox/
├── database/
│   └── document_engine.duckdb
├── runs/
├── exports/
├── review/
├── pilot/
├── logs/
└── cache/
```

---

## Installation & Environment Setup

Base installation:

```bash
python -m pip install -e ".[dev]"
```

Setup dedicated heavy worker environments (Optional):

```powershell
# Setup Docling Native & Docling OCR worker environment
.\scripts\setup_docling_env.ps1

# Setup PaddleOCR-VL fallback worker environment
.\scripts\setup_paddleocr_vl_env.ps1
```

---

## Private Real-Document Pilot Workflow

1. Copy pilot manifest template to ignored workspace directory:
   ```bash
   cp configs/pilot_manifest.example.yaml workspace/pilot/pilot_manifest.yaml
   ```
2. Configure local PDF paths in `workspace/pilot/pilot_manifest.yaml`.
3. Run private pilot processing:
   ```bash
   python scripts/run_pilot.py --manifest workspace/pilot/pilot_manifest.yaml
   ```

---

## CLI Usage

Initialize workspace:

```bash
document-engine init-workspace
```

Inspect PDF profile without OCR:

```bash
document-engine inspect "path/to/document.pdf"
```

Process single document end-to-end:

```bash
document-engine process "path/to/document.pdf"
```

Process folder of PDFs:

```bash
document-engine process-folder "path/to/pdf_folder"
```

List pending items in review queue:

```bash
document-engine review-list
```

Export run results to Excel:

```bash
document-engine export --run-id "run_20260807"
```

---

## Local Dashboard UI

Launch the Streamlit dashboard:

```bash
python scripts/run_ui.py
```
