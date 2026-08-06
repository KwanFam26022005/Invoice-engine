# Universal Invoice and Business Document Engine

A local-first enterprise document intake, inspection, parser routing, deterministic validation, DuckDB persistence, and human review system designed for complex business documents (invoices, utility statements, port services, tax withholding certificates, receipts, and supporting statements).

## Features

- **Local-First & Privacy Preserving**: Zero cloud API dependencies, zero remote network calls, no telemetry.
- **Fast Non-OCR Inspection**: PyMuPDF-based intake inspector categorizing document profiles (`native_pdf`, `scan_pdf`, `mixed_pdf`, `invalid_pdf`) without OCR overhead.
- **Profile-Aware Parser Routing**: Dispatches native PDFs to fast PyMuPDF/Docling native parsers, scanned documents to Docling OCR (EasyOCR), and handles difficult documents via PaddleOCR-VL fallback.
- **Common Document IR**: Structured representation containing pages, blocks, tables, raw geometry, parser provenance, and deterministic IDs (`doc_<sha256[:16]>`, `{doc_id}_p0001`, `{page_id}_b00001`, `{page_id}_t001`).
- **Family Classification**: Multi-anchor classifier identifying 7 distinct document families (`sales_invoice`, `utility_consumption_invoice`, `service_volume_invoice`, `port_service_invoice`, `receipt`, `tax_withholding_certificate`, `supporting_statement`) plus `unknown`.
- **Typed Schemas & Normalization**: Discriminated Pydantic business models using `Decimal` money representations and deterministic Vietnamese date/tax ID/amount/container normalizers.
- **Deterministic Validation**: Configurable tolerance financial and consumption calculations (`closing - opening * factor == consumption`).
- **DuckDB Storage**: Idempotent DDL migrations storing relational projections, evidence references, and full JSON canonical payloads within isolated per-document transactions.
- **Human Review Queue**: Built-in audit trail and correction manager for flagged or unknown documents.
- **Multi-Sheet Excel Export**: `openpyxl`-based exporter generating clean workbooks with auto-filters, frozen panes, and formula injection sanitization (`=`, `+`, `-`, `@`).

> [!NOTE]
> **Accuracy Disclaimer**: Unknown or low-completeness document layouts are routed to the human review queue rather than silently accepted.

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
├── logs/
└── cache/
```

---

## Installation

```bash
# Install package in editable mode with development dependencies
python -m pip install -e ".[dev]"
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
document-engine export --run-id "run_20260806"
```

---

## Local Dashboard UI

Launch the Streamlit dashboard:

```bash
python scripts/run_ui.py
```

---

## Archival Note

For the legacy engine benchmark implementation (v1.0.0), refer to [`docs/legacy/benchmark_v1.md`](docs/legacy/benchmark_v1.md) or checkout tag:

```bash
git checkout benchmark-v1.0.0
```
