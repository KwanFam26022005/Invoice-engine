"""Evidence collection utilities for tracing extracted values back to DocumentIR blocks and cells."""

import re
from typing import List, Optional, Tuple

from document_engine.ir.models import DocumentIR, EvidenceReference, TableCellIR, TableIR


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


def find_anchor_value(
    document_ir: DocumentIR, anchor_pattern: str, value_pattern: str = r"[^\n]+"
) -> Tuple[Optional[str], List[EvidenceReference]]:
    """Extract a same- or next-block value after a semantic anchor with evidence."""
    anchor = re.compile(anchor_pattern, re.IGNORECASE)
    value = re.compile(value_pattern)
    blocks = [block for page in document_ir.pages for block in page.blocks if block.text.strip()]
    for index, block in enumerate(blocks):
        match = anchor.search(block.text)
        if not match:
            continue
        candidates = [block.text[match.end():], *(item.text for item in blocks[index + 1 : index + 3])]
        for candidate in candidates:
            found = value.search(candidate.lstrip(" :\t\n"))
            if found:
                raw = found.group(0).strip()
                if raw:
                    return raw, [EvidenceReference(document_id=document_ir.document_id, page_number=block.page_number, block_id=block.block_id, bbox=block.geometry.bbox if block.geometry else None, source_text=raw, parser_id=document_ir.provenance.parser_id, parser_version=document_ir.provenance.parser_version)]
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
