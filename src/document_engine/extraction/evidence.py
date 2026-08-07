"""Evidence collection utilities for tracing extracted values back to DocumentIR blocks and cells."""

import re
from typing import List, Optional, Tuple

from document_engine.ir.models import BlockIR, DocumentIR, EvidenceReference, TableCellIR, TableIR


def find_text_evidence(
    document_ir: DocumentIR, regex_pattern: str
) -> Tuple[Optional[str], List[EvidenceReference]]:
    """Search DocumentIR pages/blocks for regex pattern and return match with EvidenceReference."""
    compiled_re = re.compile(regex_pattern, re.IGNORECASE)

    for page in document_ir.pages:
        for block in page.blocks:
            m = compiled_re.search(block.text)
            if m:
                matched_val = m.group(1) if m.groups() else m.group(0)
                bbox_vals = block.geometry.bbox if block.geometry else None
                ev = EvidenceReference(
                    document_id=document_ir.document_id,
                    page_number=page.page_number,
                    block_id=block.block_id,
                    bbox=bbox_vals,
                    source_text=m.group(0),
                    parser_id=document_ir.provenance.parser_id,
                    parser_version=document_ir.provenance.parser_version,
                )
                return matched_val.strip(), [ev]

    return None, []


def find_table_evidence(
    document_ir: DocumentIR, cell: TableCellIR, table: TableIR, page_num: int
) -> EvidenceReference:
    """Create EvidenceReference for a table cell."""
    bbox_vals = cell.geometry.bbox if cell.geometry else None
    return EvidenceReference(
        document_id=document_ir.document_id,
        page_number=page_num,
        table_id=table.table_id,
        cell_id=cell.cell_id,
        bbox=bbox_vals,
        source_text=cell.text,
        parser_id=document_ir.provenance.parser_id,
        parser_version=document_ir.provenance.parser_version,
    )
