# Phase 9C — Semantic Evidence Grounding

Phase 9C adds a deterministic boundary between schema-conditioned semantic extraction and canonical business data.

## Contract

Semantic extractors may propose values, but proposed values are not trusted financial truth. A candidate must first be located in immutable `DocumentIR` evidence before it can be considered grounded.

Grounding searches `BlockIR` and `TableCellIR` while preserving page, block, table, cell, bbox, parser ID, and parser version provenance.

## Match order

The grounder uses deterministic strategies in this order:

1. exact source occurrence;
2. normalized Unicode/whitespace text occurrence;
3. tax-ID canonical equality for `tax_id` fields;
4. date canonical equality for date fields;
5. Decimal canonical equality for monetary/quantity fields;
6. constrained fuzzy text matching for non-critical descriptive text only;
7. unsupported when no source evidence can be found.

Evidence hints supplied by a semantic extractor are prioritized for lookup but are not trusted. If a hint points to the wrong source region, the candidate must still match actual `DocumentIR` content before evidence is attached.

## High-risk fields

Fuzzy matching is disabled for identifier and financial-like field paths, including document numbers, tax IDs, amounts, totals, prices, quantities, dates, periods, serials, codes, readings, consumption, rates, and tax values.

This prevents near-string similarity from turning an OCR or model error into supported financial evidence.

## Candidate states

- `GROUNDED`: a deterministic source match exists and an `EvidenceReference` is attached.
- `UNSUPPORTED`: the extractor proposed a value but the value cannot be located in source evidence, or the extractor already marked it unsupported.
- `ABSTAINED`: the extractor intentionally emitted no value. Abstention remains distinct from unsupported prediction.

The grounder does not mutate `DocumentIR`, does not validate arithmetic, and does not convert candidates into `BusinessDocumentEnvelope`. Canonical resolution and deterministic business validation remain downstream responsibilities.

## Runtime and privacy

Grounding is local and deterministic. It performs no network access and loads no models. `EvidenceReference.source_text` is runtime data and must remain subject to the existing workspace/privacy rules; private source text must not be committed to Git or emitted into aggregate public-safe evaluation reports.

## Phase boundary

After Phase 9C passes local full gates, the next permitted experiment is Phase 9D: a Docling schema-conditioned semantic extraction canary. Docling semantic output must enter the system through `SemanticExtractionResult` and pass this evidence-grounding layer before any later candidate resolution or validation.
