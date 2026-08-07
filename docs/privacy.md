# Privacy & Data Protection Policy

## Local Processing Guarantee
- All document parsing, OCR, layout extraction, and canonical mapping occur strictly on the local machine.
- No raw document images, text, extracted field candidates, or ground truth values are transmitted to cloud APIs or external servers.

## Offline Operational Mode
- Runtime document processing works fully offline from local caches.
- Model prefetching is restricted to explicit user setup scripts with `ALLOW_MODEL_DOWNLOAD=1`.
- Real document files and private pilot manifests are excluded from version control via `.gitignore`.
