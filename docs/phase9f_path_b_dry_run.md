# Phase 9F.2B — Controlled CURRENT_PILOT Semantic Dry Run

This phase exercises Path B on exactly one CURRENT_PILOT document after the
Phase 9F.2B.2 eligibility probe identified a legitimate runtime-classified
candidate.

## Frozen execution boundary

The tracked adapter is `document_engine.evaluation.phase9f_path_b`.

It enforces:

- CURRENT_PILOT only;
- no holdout execution;
- no UNKNOWN_FAMILY cohort execution;
- PyMuPDF native pre-semantic preprocessing only;
- the frozen `DocumentClassifier` determines `predicted_family`;
- `supports_semantic_schema(predicted_family)` gates semantic execution;
- the semantic schema is selected from the runtime `predicted_family` only;
- manifest/audit family is never supplied to the semantic request;
- Docling/NuExtract runs local-only with network disabled;
- `EvidenceGrounder` runs before any private audit comparison;
- audit values are loaded only after inference and grounding;
- returned/persisted Phase 9F output contains structure/counts only.

The Docling semantic worker uses the frozen NuExtract model identity already
recorded by the semantic canary. This phase does not change model configuration,
prompts, schemas, classifier rules, preprocessing, or grounding thresholds.

## Runtime policy freeze

Path B runtime suitability is separate from semantic quality. The tracked policy
is:

`configs/evaluation/phase9f_path_b_runtime_policy.yaml`

The current frozen CPU evidence is:

- lightweight Docling semantic healthcheck: PASS;
- API/cache/offline/resource readiness: PASS;
- actual device: CPU;
- 180 second controlled execution: timeout;
- 600 second controlled execution: timeout;
- diagnostic blocking stage: `extraction_started`.

Therefore the current CPU verdict is:

`CPU_EXECUTION_SUITABILITY_BLOCKED`

This verdict does **not** mean that NuExtract semantic quality failed. Semantic
quality was not evaluable because the worker never returned a semantic result.
For CPU runtime, Path B can still be healthchecked but semantic canary and
production execution are blocked by policy. The deterministic fallback route is
Path A (`a_deterministic`).

CUDA-capable runtime remains canary-only until semantic extraction and evidence
grounding are reviewed and explicitly accepted. Production Path B remains false
until that acceptance is frozen in the policy.

## Probe without model loading

From the repository root:

```powershell
python scripts\run_phase9f_path_b_dry_run.py `
  --alias current_tax_001
```

Expected boundary:

```text
PHASE_9F2B_ELIGIBILITY
...
eligible=True
model_loaded=false
inference_executed=false
private_values_persisted=false
MANUAL_TERMINAL_TASK_REQUIRED
```

This command must not load the semantic model.

## Policy-gated execution

Run the runner from the base application environment. The `WorkerClient` resolves
and launches the dedicated `.venv-docling-semantic` worker interpreter.

```powershell
python scripts\run_phase9f_path_b_dry_run.py `
  --alias current_tax_001 `
  --execute
```

Before any heavy model call the runner performs a lightweight worker healthcheck,
loads the tracked runtime policy, and emits a privacy-safe decision.

On the currently frozen CPU runtime the expected result is:

```text
PHASE_9F2B_RUNTIME_POLICY
runtime_verdict=CPU_EXECUTION_SUITABILITY_BLOCKED
reason_code=CPU_EXTRACTION_TIMEOUT_CONFIRMED
actual_device=cpu
canary_allowed=False
production_allowed=False
semantic_quality_evaluable=False
selected_path=a_deterministic
fallback_path=a_deterministic
PHASE_9F2B_RUNTIME_BLOCKED
model_loaded=false
inference_executed=false
private_values_persisted=false
```

The runner intentionally does not execute Path A automatically in the same
invocation. This preserves Phase 9F path independence; it reports the fallback
route only.

On a suitable CUDA runtime the policy may return
`ACCELERATOR_CANARY_REQUIRED`, allowing exactly one Path B canary while keeping
production execution disabled until acceptance.

## Interpretation

A future successful accelerator canary would prove only that the frozen Path B
dataflow can execute on a legitimate CURRENT_PILOT document:

```text
PDF
 -> frozen PyMuPDF pre-semantic DocumentIR
 -> frozen DocumentClassifier
 -> runtime predicted_family
 -> registered semantic schema
 -> runtime policy gate
 -> Docling/NuExtract local semantic candidates
 -> deterministic EvidenceGrounder
 -> private post-inference audit comparison
 -> privacy-safe Phase9FDocumentObservation
```

It does not establish generalization accuracy and does not authorize a holdout
batch. Holdout execution remains a later explicit gate after the one-document
semantic + grounding result is reviewed and frozen.
