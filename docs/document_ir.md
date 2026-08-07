# Document Intermediate Representation (DocumentIR)

DocumentIR serves as the universal contract between Level 1 (Document Parsing) and Level 2 (Business Interpretation).

## Structural Contract
- **SourceDocument**: Document metadata, SHA-256 digest, page count.
- **DocumentProfile**: PDF classification (`native_pdf`, `scan_pdf`, `mixed_pdf`), text layer metrics.
- **ParserProvenance**: Actual parser runtime identity, version, execution time, and configuration.
- **PageIR**: Page dimensions (width, height), per-page text content, ordered blocks, and tables.
- **BlockIR**: Text blocks with reading order, label, and bounding box geometry (`[x0, y0, x1, y1]`).
- **TableIR / TableCellIR**: Structured table cells with row/column indices, header flags, text, and bounding box geometry.
