# Phase 9F — Controlled A/B/C Generalization Evaluation

Phase 9F compares three independent extraction paths on the locked Phase 9 cohorts before any hybrid resolver is introduced.

## Frozen paths

### A — deterministic baseline

Frozen baseline revision:

```text
2eb4b3f7695ef6693369d732a8520fe243269d7a
```

This path uses the existing deterministic classifier, family mapper, evidence, completeness, and validator behavior. The current branch still has the same classifier and `DocumentMapper` blobs as the R3 baseline; Phase 9F nevertheless records the frozen baseline revision explicitly.

### B — Docling semantic

Frozen semantic canary revision:

```text
87c55aff8ac4bdf03ddceab7176344eccb608ea3
```

Docling semantic extraction consumes `DocumentIR` and emits semantic candidates. `EvidenceGrounder` remains mandatory. The audited/expected family from the private manifest must never be used as a schema oracle. Schema conditioning must come from the frozen runtime classifier output. If the runtime family has no registered semantic schema, the path abstains.

### C — Paddle visual/layout

Frozen real-canary revision:

```text
b02ba775d279802fb92382ed9f564d86c016c152
```

PaddleOCR-VL produces visual/layout `DocumentIR`; the same frozen classifier/mapper/evidence/validator rules are applied downstream. The Phase 9E synthetic canary verified real local inference, block extraction, geometry, and provenance. Table count was zero in that first canary and remains a measured metric rather than a guaranteed capability.

## Fairness rules

Phase 9F enforces these rules before any path execution:

- no expected/audited family is supplied to a runtime extractor;
- no holdout tuning;
- A, B, and C remain independent until Phase 9G;
- unsupported Docling semantic families abstain rather than fabricate;
- private PDF bytes, audit values, extracted text, and absolute private paths remain outside tracked files and privacy-safe reports;
- heavyweight inference is a manual terminal gate;
- the planner never loads a model or executes inference.

## Cohorts

The locked manifest must satisfy the existing Phase 9 contract:

- `current_pilot`
- `holdout_same_family`
- `unknown_family`

The tracked contract currently requires at least 12 documents and at least four distinct layout groups. Private manifests and audit files remain under ignored `workspace/` paths.

## Metrics

The required Phase 9 metrics remain:

- exact match;
- normalized match;
- prediction precision;
- prediction recall;
- evidence coverage;
- evidence-grounded precision;
- unsupported prediction rate;
- abstention rate;
- hallucination count;
- table/line-item accuracy;
- completeness;
- validation pass rate;
- review rate;
- runtime seconds;
- peak RSS MB.

Phase 9F aggregation is field-weighted for field accuracy metrics. Runtime is reported as mean per document/path and peak RSS as the maximum observed per path. A count-only `Phase9FDocumentObservation` deliberately excludes source text, field values, filenames, and private paths.

## Plan preparation

The planner is lightweight:

```powershell
python scripts\prepare_phase9f_evaluation.py `
  --contract configs\evaluation\phase9_schema.yaml `
  --run-contract configs\evaluation\phase9f_run.yaml `
  --manifest workspace\private\phase9\phase9_manifest.yaml `
  --output workspace\phase9f\phase9f_execution_plan.json `
  --check-private-files
```

Expected terminal status:

```text
PHASE9F_PLAN_READY
model_loaded=false
inference_executed=false
private_values_persisted=false
MANUAL_TERMINAL_TASK_REQUIRED
```

The generated plan contains aliases, cohorts, layout groups, manifest family labels for evaluation bookkeeping, frozen path revisions, required metrics, and a structural fingerprint. It intentionally omits `source_ref` and `audit_ref`.

## Heavy execution boundary

Phase 9F.1 does **not** implement or run the heavyweight A/B/C batch. The next step, Phase 9F.2, is a per-path execution adapter with exactly one-document manual dry runs before any locked holdout batch is started.

Do not run Docling semantic or Paddle visual inference from Antigravity/Codex. When Phase 9F.2 reaches a real model call, print `MANUAL_TERMINAL_TASK_REQUIRED` and give the operator a dedicated PowerShell command.

## Result interpretation

Phase 9F is diagnostic, not a winner-selection shortcut. A path can be useful even when its overall exact-match rate is lower if it adds grounded evidence, table/layout recovery, safe abstention, or coverage on cases where another path fails. Hybrid selection belongs to Phase 9G only after the independent observations are frozen.

## Status

Current implementation status after this phase:

```text
PHASE_9F_1_EVALUATION_HARNESS_IMPLEMENTED_LOCAL_GATES_PENDING
```

No Phase 9F accuracy claim is valid until the private manifest is locked, the planner passes locally, and controlled path executions are completed.
