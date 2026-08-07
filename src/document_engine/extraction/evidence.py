"""Evidence collection utilities for tracing extracted values back to DocumentIR blocks and cells."""

import re
import unicodedata
from typing import List, Optional, Tuple

from document_engine.ir.models import DocumentIR, EvidenceReference, TableCellIR, TableIR


def resolve_semantic_columns(table: TableIR) -> dict[str, int]:
    """Map common invoice headers to semantic columns without positional shifts."""
    headers = {cell.col_index: unicodedata.normalize("NFD", cell.text).lower() for cell in table.cells if cell.row_index == 0}
    mapping: dict[str, int] = {}
    aliases = {"description": ("mat hang", "ten hang", "hang hoa", "dich vu", "description", "item"), "unit": ("dvt", "don vi tinh", "unit"), "quantity": ("so luong", "quantity"), "unit_price": ("don gia", "unit price"), "amount": ("thanh tien", "amount")}
    for concept, patterns in aliases.items():
        for index, header in headers.items():
            normalized = "".join(
                char for char in header if not unicodedata.combining(char)
            ).replace("đ", "d")
            if any(pattern in normalized for pattern in patterns):
                mapping[concept] = index
                break
    return mapping


def semantic_columns_are_ambiguous(table: TableIR) -> bool:
    """Return whether distinct semantic concepts resolve to one column."""
    mapping = resolve_semantic_columns(table)
    return len(mapping) != len(set(mapping.values()))


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
    """Extract a same-line or immediate next-block value after an anchor.

    Values are deliberately limited to the first non-empty logical line.  This
    prevents a following field label from becoming part of a text value while
    retaining provenance for the block that actually supplied the value.
    """
    anchor = re.compile(anchor_pattern, re.IGNORECASE)
    value = re.compile(value_pattern, re.IGNORECASE)
    for page in document_ir.pages:
        blocks = [block for block in page.blocks if block.text.strip()]
        for index, block in enumerate(blocks):
            match = anchor.search(block.text)
            if not match:
                continue
            candidates = [(block, block.text[match.end():])]
            if index + 1 < len(blocks):
                candidates.append((blocks[index + 1], blocks[index + 1].text))
            for value_block, candidate in candidates:
                candidate = candidate.lstrip(" :\t\n")
                first_line = next(
                    (line.strip() for line in candidate.splitlines() if line.strip()),
                    "",
                )
                found = value.search(first_line)
                if found:
                    raw = found.group(0).strip()
                    if raw:
                        return raw, [EvidenceReference(document_id=document_ir.document_id, page_number=value_block.page_number, block_id=value_block.block_id, bbox=value_block.geometry.bbox if value_block.geometry else None, source_text=raw, parser_id=document_ir.provenance.parser_id, parser_version=document_ir.provenance.parser_version)]
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
