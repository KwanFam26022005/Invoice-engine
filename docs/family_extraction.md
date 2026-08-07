# Evidence-Backed Family Extraction

## Specialized Family Mappers
The engine implements specialized mappers for production document families:
1. `sales_invoice`: Tax invoices, retail sales invoices, commercial invoices.
2. `utility_consumption_invoice`: Electricity (kWh) and water (m³) consumption invoices.
3. `tax_withholding_certificate`: Income tax withholding certificates (Chứng từ khấu trừ thuế TNCN).

## Field Evidence & Candidates
Every extracted candidate field contains:
- `raw_value` and `normalized_value`
- `evidence_references`: Bounding box, page number, block ID, cell ID, source text snippet.
- `extraction_method`: `native_text`, `ocr_text`, `table_cell`, `anchor_rule`.

## Disambiguation of Missing vs Zero Values
Fields are explicitly modeled using `Optional[Decimal] = None`. Unextracted or absent fields remain `None` and are not defaulted to `Decimal("0")` or arbitrary fallback strings.
