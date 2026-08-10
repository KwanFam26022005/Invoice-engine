# Phase 9F.2B.6 — Path B Fallback Acceptance / Freeze

Phase 9F.2B.6 freezes the controlled fallback result produced by Phase 9F.2B.5.
It deliberately separates routing acceptance from deterministic extraction quality.

## Frozen current-pilot result

For `current_tax_001`, the runtime policy selected Path A because the local CPU
Path B runtime is blocked by the previously confirmed 180 s and 600 s timeouts at
`extraction_started`.

The privacy-safe fallback observation is frozen in:

`configs/evaluation/phase9f_path_b_fallback_acceptance.yaml`

The frozen routing result is:

- runtime verdict: `CPU_EXECUTION_SUITABILITY_BLOCKED`;
- selected path: `a_deterministic`;
- fallback path: `a_deterministic`;
- Path B inference executed: `false`;
- Path A executed: `true`;
- fallback verified: `true`;
- routing accepted: `true`.

The frozen Path A observation is count/boolean only:

- predicted family: `tax_withholding_certificate`;
- family match: `true`;
- confirmed fields: 13;
- predicted fields: 7;
- normalized matches: 2;
- validation pass: `false`;
- review required: `true`;
- parser: `pymupdf_native`.

These counts do not contain source text, extracted values, filenames, host paths,
or private audit values.

## Acceptance semantics

Successful routing does **not** imply successful extraction quality.

The current freeze therefore records:

- `routing_accepted=true`;
- `fallback_execution_accepted=true`;
- `fallback_quality_disposition=REVIEW_REQUIRED`;
- `fallback_quality_accepted=false`;
- `semantic_path_b_quality_evaluable=false`;
- `semantic_path_b_quality_accepted=false`;
- `holdout_authorized=false`;
- `generalization_claim_authorized=false`.

No threshold is introduced from the 2/13 normalized-match pilot result. This phase
must not tune Path A, Path B, the classifier, semantic schema, mapper rules, or
grounding logic from the controlled current-pilot observation.

## Local validation

After Phase 9F.2B.5 produced:

`workspace/phase9f/path_b_fallback_verification.json`

run:

```powershell
python scripts\freeze_phase9f_path_b_fallback_acceptance.py
```

Expected boundary:

```text
PHASE_9F2B6_FALLBACK_ACCEPTANCE
routing_accepted=true
fallback_execution_accepted=true
fallback_quality_disposition=REVIEW_REQUIRED
fallback_quality_accepted=false
semantic_path_b_quality_evaluable=false
semantic_path_b_quality_accepted=false
holdout_authorized=false
generalization_claim_authorized=false
freeze_validated=true
private_values_persisted=false
```

The output under `workspace/phase9f/` is ignored and contains only the privacy-safe
acceptance model.

## What this phase proves

Phase 9F.2B.6 proves that the frozen runtime policy routes an unsuitable CPU Path B
runtime to the deterministic Path A fallback and that the observed fallback result
matches the tracked privacy-safe freeze.

It does not prove that Path A field extraction is production-quality for this
family, and it does not provide any evidence about NuExtract semantic quality.
Path B semantic evaluation remains blocked until an accelerator-backed canary can
complete inference and grounding under the frozen schema/classifier contract.
