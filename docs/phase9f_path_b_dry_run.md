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

## Real one-document dry run

Run only from the dedicated local semantic environment after the offline model
cache/artifacts readiness check passes:

```powershell
python scripts\run_phase9f_path_b_dry_run.py `
  --alias current_tax_001 `
  --execute
```

The command performs exactly one semantic execution and writes a privacy-safe
count-only result under ignored `workspace/phase9f/`.

Do not switch the alias to a holdout document. Do not use the manifest family to
select the schema. Do not tune the classifier, semantic template, model, or
grounder from the result of this dry run.

## Interpretation

A successful dry run proves only that the frozen Path B dataflow can execute on
a legitimate CURRENT_PILOT document:

```text
PDF
 -> frozen PyMuPDF pre-semantic DocumentIR
 -> frozen DocumentClassifier
 -> runtime predicted_family
 -> registered semantic schema
 -> Docling/NuExtract local semantic candidates
 -> deterministic EvidenceGrounder
 -> private post-inference audit comparison
 -> privacy-safe Phase9FDocumentObservation
```

It does not establish generalization accuracy and does not authorize a holdout
batch. Holdout execution remains a later explicit gate after this one-document
result is reviewed and frozen.
