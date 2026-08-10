# Phase 9F.2B.5 — Path B Fallback / Routing Verification

Phase 9F.2B.5 verifies that the frozen Path B runtime policy is not only reported
but is enforced by an independent Path A execution when Path B is blocked.

## Frozen boundary

For the current CPU runtime, the tracked policy records:

```text
runtime_verdict=CPU_EXECUTION_SUITABILITY_BLOCKED
reason_code=CPU_EXTRACTION_TIMEOUT_CONFIRMED
fallback_path=a_deterministic
```

The verification flow is:

```text
Path B healthcheck
 -> frozen Path B runtime policy
 -> runtime decision
 -> selected path
 -> require selected_path == a_deterministic
 -> execute standalone Path A observation
 -> require observation.path == a_deterministic
 -> persist privacy-safe counts/metadata only
```

The verification runner never executes Docling/NuExtract inference. It performs a
lightweight Path B healthcheck only so the runtime decision is based on the actual
current device while the CPU timeout evidence remains frozen in the tracked policy.

## Run

From the repository root:

```powershell
python scripts\run_phase9f_path_b_fallback_verification.py `
  --alias current_tax_001
```

Expected high-level result on the frozen CPU runtime:

```text
PHASE_9F2B5_FALLBACK_VERIFICATION
runtime_verdict=CPU_EXECUTION_SUITABILITY_BLOCKED
reason_code=CPU_EXTRACTION_TIMEOUT_CONFIRMED
purpose=canary
selected_path=a_deterministic
fallback_path=a_deterministic
path_b_inference_executed=false
path_a_executed=true
fallback_verified=true
...
private_values_persisted=false
```

## Fairness and privacy

- Path B inference is not executed.
- Path A produces its own `Phase9FDocumentObservation` with
  `path=a_deterministic`.
- The runner does not merge Path A counts into a Path B observation.
- The manifest family is not used to choose the Path B schema.
- Only the existing Path A privacy-safe observation and an allowlisted metadata
  subset are persisted.
- Source text, filenames, absolute paths, raw extracted values, and audit values
  are not persisted.

## Gate

Phase 9F.2B.5 passes only when all of the following hold:

```text
selected_path == a_deterministic
fallback_path == a_deterministic
path_b_inference_executed == false
path_a_executed == true
path_a_observation.path == a_deterministic
fallback_verified == true
```

A CUDA runtime whose canary is still allowed must fail this fallback-only runner
with `PATH_B_FALLBACK_NOT_SELECTED`; it must not be misreported as a Path A
fallback.
