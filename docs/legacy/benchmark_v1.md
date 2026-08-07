# Benchmark Engine v1.0.0 Legacy Archive

> [!NOTE]
> This document archives the historical context of the benchmark-focused version of `Invoice-engine`.

## Version Summary

- **Baseline Tag**: `benchmark-v1.0.0`
- **Migration Date**: 2026-08-06
- **Original Focus**: Benchmarking local PDF extraction engines (Docling, PP-StructureV3, EasyOCR) across performance and correctness tracks for Vietnamese logistics documents.

## Architectural Pivot

The repository was transitioned from an engine benchmark tool to an **End-to-End Enterprise Document Processing System** (`document_engine`). Engine comparison, latency ranking, leaderboard calculations, and measured repeat campaigns have been removed in favor of:

1. Fast non-OCR PDF profile inspection (`PyMuPDF`).
2. Profile-aware single-parser routing (`pymupdf_native`, `docling_ocr`, `paddleocr_vl` fallback).
3. Common Document IR with deterministic IDs (`doc_`, `p`, `b`, `t`).
4. Rule-based family classification for 7 business families (`sales_invoice`, `utility_consumption_invoice`, `service_volume_invoice`, `port_service_invoice`, `receipt`, `tax_withholding_certificate`, `supporting_statement`) plus `unknown`.
5. Canonical Pydantic schemas using `Decimal` money representation.
6. Deterministic validation engine with configurable tolerances.
7. Local DuckDB persistence with isolated per-document transactions.
8. Human review queue and correction audit trail.
9. Multi-sheet Excel workbook export (`openpyxl`).

## Checkout Legacy Code

To check out the legacy benchmark implementation and campaign runner, run:

```bash
git checkout benchmark-v1.0.0
```
