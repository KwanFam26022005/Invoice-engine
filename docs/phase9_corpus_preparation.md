# Phase 9 Private Corpus Preparation Guide

This guide details the onboarding workflow and privacy requirements for assembling the real private Phase 9 evaluation corpus.

## Target Composition Recommendation

To achieve a balanced evaluation across mature schemas and unknown families, the recommended minimum composition of 12 real documents is:

- **3 Current Pilot Documents**:
  - 1 `sales_invoice`
  - 1 `utility_consumption_invoice`
  - 1 `tax_withholding_certificate`

- **6 Same-Family Holdout Documents** (Never used for prior R2/R3 tuning):
  - 2 `sales_invoice`
  - 2 `utility_consumption_invoice`
  - 2 `tax_withholding_certificate`

- **3 Unknown-Family Real Documents**:
  - Real evaluation documents from families outside the three mature Phase 9 semantic schemas (e.g., receipt, shipping manifest, bank statement, port service invoice, supporting statement).

> [!IMPORTANT]
> **No Synthetic PDFs**: Synthetic PDFs must never be used to satisfy the real generalization corpus.
>
> **UNKNOWN_FAMILY Definition**: The `unknown_family` cohort specifically tests how extraction models handle document types outside the mature specialized mapper families.

## Minimum Phase 9 Contract Requirements

The formal contract (`configs/evaluation/phase9_schema.yaml`) enforces:
1. `minimum_documents` = 12
2. `minimum_layout_groups` = 4
3. All three required cohorts represented: `current_pilot`, `holdout_same_family`, `unknown_family`
4. `allow_holdout_tuning` = `false`
5. Real source PDFs and audited JSON files for every document entry.

## CLI Intake Tooling Workflow

### 1. Register a Private Document

Register a candidate PDF into `workspace/private/phase9/corpus_registry.yaml`:

```bash
python scripts/register_phase9_document.py \
    --source workspace/private/phase9/documents/doc_001.pdf \
    --alias holdout_sales_001 \
    --family sales_invoice \
    --cohort holdout_same_family \
    --layout-group sales_layout_b \
    --audit workspace/private/phase9/audit/holdout_sales_001.audit.json \
    --used-for-prior-tuning false
```

- SHA256 hashes are automatically computed for duplicate rejection.
- Documents used for prior tuning will be rejected from the `holdout_same_family` cohort.

### 2. Generate an Audit Skeleton

Create a private audit JSON skeleton with empty fields starting as `NOT_AUDITED` and `expected: null`:

```bash
python scripts/create_phase9_audit_skeleton.py \
    --alias holdout_sales_001 \
    --family sales_invoice \
    --output workspace/private/phase9/audit/holdout_sales_001.audit.json
```

### 3. Inspect Corpus Readiness

Check corpus readiness and deficit statistics:

```bash
python scripts/check_phase9_corpus_readiness.py \
    --registry workspace/private/phase9/corpus_registry.yaml \
    --contract configs/evaluation/phase9_schema.yaml
```

### 4. Generate the Private Manifest

When the corpus meets all readiness requirements, lock the private manifest:

```bash
python scripts/build_phase9_manifest.py \
    --registry workspace/private/phase9/corpus_registry.yaml \
    --contract configs/evaluation/phase9_schema.yaml \
    --output workspace/private/phase9/phase9_manifest.yaml
```

## Privacy & Security Boundary

- All private documents, audits, registries, and manifests remain under `workspace/private/` which is ignored by `.gitignore`.
- All paths referenced in manifests and registries must be workspace-relative (`workspace/...`).
- No private filenames, absolute paths, raw PDF bytes, extracted text, or audit expected values may be printed in public logs or committed to git.
