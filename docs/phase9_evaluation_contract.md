# Phase 9A/B — Generalization Evaluation and Semantic Extraction Contracts

## Frozen baseline

Phase 9 starts from the immutable R3 revision:

`2eb4b3f7695ef6693369d732a8520fe243269d7a`

The R3 implementation remains the deterministic baseline. Phase 9 does not
retune R3 using holdout values.

## 9A — Generalization evaluation contract

Phase 9 separates documents into three cohorts:

1. `current_pilot`: existing pilot documents used only as historical reference.
2. `holdout_same_family`: unseen layouts/templates from already-supported families.
3. `unknown_family`: document families that do not yet have production mappers.

The tracked manifest is an example only. Real PDFs, private audit JSON, raw OCR
text, absolute source paths, and generated reports remain under ignored
`workspace/`.

The holdout set must be locked before any Docling semantic or PaddleOCR-VL
canary is measured. Post-measurement tuning against holdout values is not
allowed in the same revision.

### Required metrics

Phase 9 retains exact/normalized matching, evidence coverage, completeness,
validation and review status, and adds:

- prediction precision and recall;
- evidence-grounded precision;
- unsupported-prediction rate;
- abstention rate;
- hallucination count;
- table/line-item accuracy;
- runtime and peak RSS.

`null`/abstention is preferred to an unsupported fabricated value. These are
evaluation metrics and must not be described as generic system accuracy.

## 9B — Semantic extraction boundary

Semantic engines are candidate generators, not authorities.

The boundary is:

```text
DocumentIR / optional local page image refs
        |
        v
SemanticExtractor
        |
        v
SemanticExtractionResult
        |
        v
SemanticCandidate[]
```

A candidate contains a canonical field path, proposed value, optional raw value,
confidence, source method, and optional structural evidence hints. It is not a
`FieldCandidate` and is not written into `BusinessDocumentEnvelope` by these
contracts.

Later Phase 9C evidence grounding is responsible for attaching authoritative
`EvidenceReference` objects. Deterministic validation remains downstream and
authoritative for financial arithmetic and acceptance/review decisions.

### Local-first constraints

The default runtime policy is:

- local runtime only;
- network disabled;
- abstain when uncertain;
- no automatic promotion from semantic output to financial truth.

Online model preparation, if required by future optional engines, must be a
separate explicit setup step and is not part of these runtime contracts.

## Implementation files

- `configs/evaluation/phase9_schema.yaml`
- `configs/evaluation/phase9_manifest.example.yaml`
- `src/document_engine/evaluation/phase9_contract.py`
- `src/document_engine/semantic/contracts.py`
- `tests/unit/test_phase9_evaluation_contract.py`
- `tests/unit/test_semantic_contracts.py`

No Docling semantic model, PaddleOCR-VL inference, evidence grounder, hybrid
resolver, or production pipeline change is introduced by Phase 9A/B.
