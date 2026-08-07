# Private Real-Document Pilot Workflow

## Overview
The private real-document pilot tests the pipeline end-to-end on real local document samples without committing confidential business documents or ground truth values to version control.

## Execution Procedure
1. Create a local manifest file: `workspace/pilot/pilot_manifest.yaml` (ignored by `.gitignore`).
2. Populate entry paths using `configs/pilot_manifest.example.yaml` as reference.
3. Execute pilot runner:
   ```powershell
   python scripts/run_pilot.py --manifest workspace/pilot/pilot_manifest.yaml
   ```
4. Audit results manually in DuckDB or stdout summary (`PASS`, `NEEDS_REVIEW`, `FAIL`).
