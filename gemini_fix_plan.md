# Universal Document Engine Fix Plan

## 1. Executive Summary

- **Current Repository Status**: The `Invoice-engine` codebase has been refactored in-place into `document_engine` (`src/document_engine/`). Legacy benchmark code (`src/document_benchmark/`) has been completely purged from the branch.
- **Test Suite Status**: 26 pytest tests pass successfully (0 failures) in 4.79s.
- **Ruff Linter Status**: Fails with **21 errors** across 11 files (`14 RUF059`, `3 SIM102`, `2 TRY201`, `1 C414`, `1 UP007`).
- **Optional Dependency Isolation Status**: Top-level module imports (`import document_engine`, `import document_engine.routing.parser_router`, `import document_engine.parsers.registry`) do **not** trigger eager loading of `paddle`, `paddleocr`, or `docling`. However, during `ParserRouter` fallback execution in `tests/unit/test_parser_router.py`, `PaddleOCRVLParser.healthcheck()` is invoked against the default registry without `importlib.util.find_spec()` isolation, causing Paddle C++ extension initialization warnings ("No ccache found") when run inside an environment where Paddle is installed.
- **Merge Readiness**: `NOT_READY` until Ruff errors are fixed, parser healthchecks use `find_spec`, unit tests use isolated test registries with fake parsers, and whitespace warnings are cleaned.

---

## 2. Verified Git State

- **Current Branch**: `agent/refactor-universal-document-engine`
- **HEAD Commit**: `540337927ab03d0647813dd2ec94239dd2a50bd6`
- **Base Commit (`origin/main`)**: `ecaf58ccd4cf3e66cd4840e487e820b3839d1294`
- **Baseline Tag**: `benchmark-v1.0.0` (Points to `ecaf58ccd4cf3e66cd4840e487e820b3839d1294`)
- **Working Tree**: Dirty (`?? ruff_errors.txt` present as untracked file).
- **Remote Status**: Up to date with origin tracking branch `agent/refactor-universal-document-engine`.

---

## 3. Complete Ruff Findings

Below is the complete table of all **21 Ruff errors** detected by `python -m ruff check src tests scripts --output-format concise`:

| # | Rule | File | Line | Message | Root Cause | Safe Fix | Risk |
|---|---|---|---:|---|---|---|---|
| 1 | `RUF059` | `scripts/run_ui.py` | 52:34 | Unpacked variable `results` is never used | `summary, results = pipeline.process_folder(...)` receives `results` but only `summary` is displayed. | Rename `results` to `_results` | None |
| 2 | `SIM102` | `scripts/run_ui.py` | 109:13 | Use a single `if` statement instead of nested `if` statements | `if st.button(...): if field_name and new_val:` nested unnecessarily. | Combine with `if st.button(...) and field_name and new_val:` | None |
| 3 | `RUF059` | `src/document_engine/cli.py` | 85:18 | Unpacked variable `results` is never used | `summary, results = pipeline.process_folder(...)` receives `results` but CLI only prints summary. | Rename `results` to `_results` | None |
| 4 | `SIM102` | `src/document_engine/export/exporter.py` | 18:9 | Use a single `if` statement instead of nested `if` statements | `if isinstance(val, str): if val.startswith(...):` nested unnecessarily. | Combine into `if isinstance(val, str) and val.startswith(...):` | None |
| 5 | `RUF059` | `src/document_engine/extraction/mapper.py` | 120:14 | Unpacked variable `status` is never used | `val, status, _ = parse_date(...)` unpacks `status` without reading. | Rename `status` to `_status` | None |
| 6 | `RUF059` | `src/document_engine/extraction/mapper.py` | 161:18 | Unpacked variable `status` is never used | `val, status, _ = parse_decimal(...)` unpacks `status` without reading. | Rename `status` to `_status` | None |
| 7 | `C414` | `src/document_engine/orchestration/pipeline.py` | 101:21 | Unnecessary `list()` call within `sorted()` | `sorted(list(folder_path.glob("*.pdf")))` wraps iterator redundantly. | Simplify to `sorted(folder_path.glob("*.pdf"))` | None |
| 8 | `TRY201` | `src/document_engine/review/review_manager.py` | 133:23 | Use `raise` without specifying exception name | `except Exception as e: ... raise e` re-raises explicit variable. | Replace `raise e` with bare `raise` | None |
| 9 | `SIM102` | `src/document_engine/routing/parser_router.py` | 119:9 | Use a single `if` statement instead of nested `if` statements | `if profile.pdf_profile == ...: if len(...) < 10:` nested unnecessarily. | Combine with `and` | None |
| 10 | `UP007` | `src/document_engine/schemas/family_schemas.py` | 208:20 | Use `X \| Y` for type annotations | `CanonicalPayload = Union[...]` uses legacy `typing.Union`. | Replace with `SalesInvoicePayload \| UtilityConsumptionInvoicePayload \| ...` | None |
| 11 | `TRY201` | `src/document_engine/storage/database.py` | 266:23 | Use `raise` without specifying exception name | `except Exception as e: ... raise e` re-raises explicit variable. | Replace `raise e` with bare `raise` | None |
| 12 | `RUF059` | `tests/unit/test_intake_inspector.py` | 50:5 | Unpacked variable `source_doc` is never used | `source_doc, profile = inspector.inspect(...)` unpacks `source_doc` without assertion. | Rename `source_doc` to `_source_doc` | None |
| 13 | `RUF059` | `tests/unit/test_normalizers.py` | 17:23 | Unpacked variable `warnings` is never used | `val_dash, status, warnings = normalize_tax_id(...)` unpacks `warnings` without check. | Rename `warnings` to `_warnings` | None |
| 14 | `RUF059` | `tests/unit/test_normalizers.py` | 24:9 | Unpacked variable `s1` is never used | `v1, s1, _ = parse_decimal(...)` unpacks `s1` without assertion. | Rename `s1` to `_s1` | None |
| 15 | `RUF059` | `tests/unit/test_normalizers.py` | 28:9 | Unpacked variable `s2` is never used | `v2, s2, _ = parse_decimal(...)` unpacks `s2` without assertion. | Rename `s2` to `_s2` | None |
| 16 | `RUF059` | `tests/unit/test_normalizers.py` | 32:9 | Unpacked variable `s3` is never used | `v3, s3, _ = parse_decimal(...)` unpacks `s3` without assertion. | Rename `s3` to `_s3` | None |
| 17 | `RUF059` | `tests/unit/test_normalizers.py` | 36:9 | Unpacked variable `s4` is never used | `v4, s4, _ = parse_decimal(...)` unpacks `s4` without assertion. | Rename `s4` to `_s4` | None |
| 18 | `RUF059` | `tests/unit/test_normalizers.py` | 40:9 | Unpacked variable `s5` is never used | `v5, s5, _ = parse_decimal(...)` unpacks `s5` without assertion. | Rename `s5` to `_s5` | None |
| 19 | `RUF059` | `tests/unit/test_normalizers.py` | 45:9 | Unpacked variable `s1` is never used | `d1, s1, _ = parse_date(...)` unpacks `s1` without assertion. | Rename `s1` to `_s1` | None |
| 20 | `RUF059` | `tests/unit/test_normalizers.py` | 48:9 | Unpacked variable `s2` is never used | `d2, s2, _ = parse_date(...)` unpacks `s2` without assertion. | Rename `s2` to `_s2` | None |
| 21 | `RUF059` | `tests/unit/test_normalizers.py` | 51:9 | Unpacked variable `s3` is never used | `d3, s3, _ = parse_date(...)` unpacks `s3` without assertion. | Rename `s3` to `_s3` | None |

---

## 4. Root-Cause Analysis

The 21 Ruff errors fall into 5 distinct categories:

1. **Unused Unpacked Variables (`RUF059` - 14 instances)**:
   - Caused by tuple unpacking syntax in test assertions and helper calls where only specific elements of returned tuples are evaluated.
   - Solution: Prefix all unused target variables with an underscore (e.g. `_status`, `_s1`, `_source_doc`).

2. **Collapsible Nested If Statements (`SIM102` - 3 instances)**:
   - Caused by writing consecutive `if A:` followed immediately by `if B:` without an `else` block.
   - Solution: Combine into `if A and B:` for cleaner control flow.

3. **Verbose Exception Re-raising (`TRY201` - 2 instances)**:
   - Caused by writing `except Exception as e: conn.execute("ROLLBACK;"); raise e`. Re-raising `e` explicitly modifies tracebacks unnecessarily.
   - Solution: Replace with bare `raise`.

4. **Redundant Sequence Casting (`C414` - 1 instance)**:
   - Caused by writing `sorted(list(folder_path.glob("*.pdf")))`. `sorted()` accepts generators directly.
   - Solution: Remove `list()`.

5. **Legacy Type Union Annotations (`UP007` - 1 instance)**:
   - Caused by `CanonicalPayload = Union[...]` in `family_schemas.py`.
   - Solution: Convert to Python 3.10 standard `A | B | C` pipe syntax.

---

## 5. Optional Dependency Isolation Findings

### Investigation Findings
- **Top-Level Package Import**: Importing `document_engine`, `document_engine.routing.parser_router`, or `document_engine.parsers.registry` does **not** load `paddle`, `paddleocr`, `docling`, or `easyocr` into `sys.modules`.
- **Eager Healthcheck Trigger**: In `PaddleOCRVLParser.healthcheck()` (lines 44-57 of `paddleocr_vl.py`), availability is checked using:
  ```python
  import paddle  # noqa: F401
  import paddleocr  # noqa: F401
  ```
  When executed inside `.venv-paddle3` (where `paddle` is installed), `import paddle` triggers Paddle's C++ extension loader (`paddle.utils.cpp_extension`), printing `"No ccache found."`.
- **Unit Test Contamination**: In `tests/unit/test_parser_router.py`, `test_fallback_trigger_on_empty_primary_output` instantiates `ParserRouter()` without passing a custom test registry. `ParserRouter` defaults to `default_registry`, which contains `PaddleOCRVLParser`. When `route_and_parse(..., enable_fallback=True)` executes, `_get_available_parser("paddleocr_vl")` calls `healthcheck()`, triggering `import paddle` at test runtime.

### Required Remediations
1. **Refactor Parser Healthchecks**: Replace eager `import paddle` / `import docling` in `healthcheck()` methods with `importlib.util.find_spec("paddle")` and `importlib.util.find_spec("paddleocr")`. This inspects module metadata without loading heavy C++ extensions or frameworks into memory.
2. **Isolate Router Unit Tests**: Update `test_parser_router.py` to register lightweight `FakeParser` fixtures into a local `ParserRegistry` instance rather than relying on `default_registry`.
3. **Subprocess Import Test**: Add a unit test verifying that `import document_engine` and `ParserRegistry()` do not populate `sys.modules` with `paddle` or `docling`.

---

## 6. Test Coverage Assessment

| Capability | Implemented | Tested | Test Quality | Missing Coverage |
|---|---|---|---|---|
| Native PDF Inspection | Yes (`inspector.py`) | Yes (`test_intake_inspector.py`) | High (uses fitz synthetic PDF) | Borderline character density thresholds |
| Scan PDF Inspection | Yes (`inspector.py`) | No | Missing | Image-only raster PDF fixture |
| Mixed PDF Inspection | Yes (`inspector.py`) | No | Missing | Multi-page mixed native/scan PDF fixture |
| Invalid / Corrupt PDF | Yes (`inspector.py`) | Yes (`test_intake_inspector.py`) | High | Missing `%PDF` header check |
| Deterministic IDs & IR | Yes (`ir/models.py`) | Yes (`test_ir_and_identifiers.py`) | High | Multi-table cell IDs |
| Profile-Aware Parser Router | Yes (`parser_router.py`) | Partial (`test_parser_router.py`) | Medium (relies on real registry) | Router tests using isolated `FakeParser` |
| Fallback Trigger Policy | Yes (`parser_router.py`) | Partial (`test_parser_router.py`) | Medium (triggers real healthcheck) | Fallback trigger isolation test |
| Document Classification (7 families + unknown) | Yes (`classifier.py`) | Partial (`test_classifier.py`) | High for 4 families | Utility, service volume, receipt, supporting statement tests |
| Typed Family Schemas (Decimal) | Yes (`family_schemas.py`) | Yes (`test_family_schemas.py`) | High | Full payload serialization test |
| Field Normalization | Yes (`normalizer.py`) | Yes (`test_normalizers.py`) | High | Invalid date formats, text normalization edge cases |
| Business Validation Engine | Yes (`validator.py`) | Yes (`test_validation_engine.py`) | High | Port service TEU math & tax cert checks |
| DuckDB Storage & Transaction Isolation | Yes (`database.py`) | Yes (`test_duckdb_storage.py`) | High | Transaction rollback error handling |
| Human Review Queue & Corrections | Yes (`review_manager.py`) | Yes (`test_review_queue.py`) | High | Concurrent review status updates |
| Excel Multi-Sheet Export & Formula Protection | Yes (`exporter.py`) | Partial (`test_universal_pipeline_e2e.py`) | Medium | Direct test for formula injection prefixing (`=`, `+`, `-`, `@`) |
| CLI Commands | Yes (`cli.py`) | Indirect (`test_universal_pipeline_e2e.py`) | Medium | Dedicated CLI argument parser tests |
| Streamlit UI Dashboard | Yes (`scripts/run_ui.py`) | No | Missing | Headless UI smoke test |
| Batch Continue-on-Error | Yes (`pipeline.py`) | Yes (`test_universal_pipeline_e2e.py`) | High | Exception recovery in single file |
| Isolated Import Verification | Yes | No | Missing | Subprocess `sys.modules` check |

---

## 7. Security and Privacy Findings

- **Path Containment / Directory Traversal**: `PDFInspector` and `DocumentPipeline` resolve inputs using `.resolve()`. All database files and exports are contained within `workspace_root`. (**Severity: Informational**).
- **YAML Safe Loading**: `AppConfig.load_from_file()` uses `yaml.safe_load()`. (**Severity: Informational**).
- **SQL Injection**: `DuckDBStorage` uses parameterized SQL queries (`?`) across all DDL and DML operations. (**Severity: Informational**).
- **Excel Formula Injection**: `ExcelExporter.sanitize_cell_value()` prefixes strings starting with `=`, `+`, `-`, `@` with `'`. (**Severity: Informational**).
- **No Unsafe Execution**: Codebase contains 0 calls to `eval()`, `exec()`, `pickle`, or `subprocess(shell=True)`. (**Severity: Informational**).
- **No Tracked Binary Files or PII**: 0 `.pdf`, `.duckdb`, `.xlsx`, or real tax IDs / personal phone numbers tracked in Git diff against `origin/main`. (**Severity: Informational**).

---

## 8. Implementation Gaps

1. **PaddleOCR-VL Fallback Adapter Parsing**: `PaddleOCRVLParser.parse()` currently returns synthetic fallback blocks rather than executing actual PaddleOCR model calls when Paddle is installed. (**Status: Partially Implemented / Adapter Stub**).
2. **Missing Inspection Test Cases**: Unit tests currently lack synthetic raster image-only and mixed native/scan PDF fixtures in `test_intake_inspector.py`. (**Status: Missing Test Coverage**).
3. **Missing Excel Formula Protection Unit Test**: Exporter formula protection is implemented in `exporter.py` but lacks explicit unit test assertions in `test_excel_export.py`. (**Status: Missing Test Coverage**).
4. **Git Whitespace Check Warning**: `git diff origin/main...HEAD --check` flags a trailing blank line at EOF in `src/document_engine/core/exceptions.py`. (**Status: Formatting Cleanup Needed**).

---

## 9. Ordered Repair Plan

### Patch 1: Ruff Codebase Cleanup & Formatting
- **Goal**: Resolve all 21 Ruff linter errors and git whitespace check warnings without changing runtime behavior.
- **Target Files**:
  - `scripts/run_ui.py` (`RUF059`, `SIM102`)
  - `src/document_engine/cli.py` (`RUF059`)
  - `src/document_engine/export/exporter.py` (`SIM102`)
  - `src/document_engine/extraction/mapper.py` (`RUF059`)
  - `src/document_engine/orchestration/pipeline.py` (`C414`)
  - `src/document_engine/review/review_manager.py` (`TRY201`)
  - `src/document_engine/routing/parser_router.py` (`SIM102`)
  - `src/document_engine/schemas/family_schemas.py` (`UP007`)
  - `src/document_engine/storage/database.py` (`TRY201`)
  - `src/document_engine/core/exceptions.py` (Remove trailing blank line at EOF)
  - `tests/unit/test_intake_inspector.py` (`RUF059`)
  - `tests/unit/test_normalizers.py` (`RUF059`)
- **Verification Command**: `python -m ruff check src tests scripts` (Must return 0 errors).
- **Risk**: Zero.
- **Proposed Commit Message**: `style: fix ruff linter errors and whitespace warnings`

### Patch 2: Non-Eager Healthchecks & Optional Dependency Isolation
- **Goal**: Prevent optional engine healthchecks (`healthcheck()`) from importing `paddle`, `paddleocr`, or `docling` modules eagerly.
- **Target Files**:
  - `src/document_engine/parsers/paddleocr_vl.py` (Use `importlib.util.find_spec("paddle")` and `find_spec("paddleocr")`)
  - `src/document_engine/parsers/docling_native.py` (Use `importlib.util.find_spec("docling")`)
  - `src/document_engine/parsers/docling_ocr.py` (Use `importlib.util.find_spec("docling")` and `find_spec("easyocr")`)
- **Verification Command**: `python -c "import document_engine.parsers.registry; import sys; assert 'paddle' not in sys.modules"`
- **Risk**: Low.
- **Proposed Commit Message**: `refactor: use find_spec for non-eager parser healthchecks`

### Patch 3: Isolated Parser Router Unit Tests
- **Goal**: Decouple `test_parser_router.py` from `default_registry` by injecting lightweight `FakeParser` test fixtures.
- **Target Files**:
  - `tests/unit/test_parser_router.py` (Define `FakeNativeParser`, `FakeOCRParser`, `FakeFallbackParser`; register into a isolated test `ParserRegistry`).
- **Verification Command**: `python -m pytest tests/unit/test_parser_router.py -v` (Must pass without emitting "No ccache found" warning).
- **Risk**: Low.
- **Proposed Commit Message**: `test: isolate parser router unit tests with fake parser registry`

### Patch 4: Expanded Test Coverage & Subprocess Import Guards
- **Goal**: Add missing unit tests for scan/mixed PDF inspection, Excel formula protection, and subprocess import isolation.
- **Target Files**:
  - `tests/unit/test_intake_inspector.py` (Add scan PDF & mixed PDF synthetic tests)
  - `tests/unit/test_excel_export.py` (Add formula injection prefixing test)
  - `tests/unit/test_dependency_isolation.py` (Add subprocess module isolation test)
- **Verification Command**: `python -m pytest -v --tb=short`
- **Risk**: Low.
- **Proposed Commit Message**: `test: add scan/mixed intake inspection, excel protection, and import isolation tests`

### Patch 5: Documentation & Final Quality Gates
- **Goal**: Ensure clean documentation, pyproject configurations, and final quality acceptance.
- **Target Files**:
  - `README.md`
  - `pyproject.toml`
- **Verification Command**: `python -m compileall -q src tests scripts; python -m pip check; document-engine --help`
- **Risk**: Low.
- **Proposed Commit Message**: `docs: finalize documentation and verification quality gates`

---

## 10. Proposed Patch Sequence

```text
Patch 1: style: fix ruff linter errors and whitespace warnings
Patch 2: refactor: use find_spec for non-eager parser healthchecks
Patch 3: test: isolate parser router unit tests with fake parser registry
Patch 4: test: add scan/mixed intake inspection, excel protection, and import isolation tests
Patch 5: docs: finalize documentation and verification quality gates
```

---

## 11. Final Acceptance Criteria

1. **Ruff Linter**: `python -m ruff check src tests scripts` passes with **0 errors**.
2. **Compilation**: `python -m compileall -q src tests scripts` passes cleanly with code 0.
3. **Pytest Suite**: `python -m pytest -v --tb=short` passes **26+ tests** with 0 failures and 0 Paddle warnings.
4. **Dependency Isolation**: Importing `document_engine` or `ParserRegistry` in a fresh Python process populates **0 heavy modules** (`paddle`, `docling`, `easyocr`) in `sys.modules`.
5. **Pip Integrity**: `python -m pip check` reports "No broken requirements found."
6. **CLI Integrity**: `document-engine --help` and `document-engine init-workspace` execute successfully with code 0.
7. **Clean Git Diff**: `git diff origin/main...HEAD --check` returns 0 whitespace warnings.
8. **No Sensitive Artifacts**: 0 real customer PDFs, DuckDB binaries, or plain text PII tracked in Git.

---

## 12. Blockers and Open Decisions

- **Working Tree Untracked File**: `git status --short` shows `?? ruff_errors.txt`. This untracked file does not block planning, but should be removed or ignored before final PR submission.
- **PaddleOCR-VL Implementation Depth**: The current `PaddleOCRVLParser.parse()` provides a compliant adapter contract and fallback IR, but defers full model weights loading to optional engine environments. This is consistent with project guidelines (no model loading in default test runs).
