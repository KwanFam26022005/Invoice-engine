"""Unit tests for Common Document IR models and deterministic identifiers."""

import hashlib
from document_engine.ir.models import (
    BlockIR,
    DocumentIR,
    DocumentProfile,
    Geometry,
    PageIR,
    ParserProvenance,
    SourceDocument,
    generate_block_id,
    generate_cell_id,
    generate_document_id,
    generate_page_id,
    generate_table_id,
)
from document_engine.core.models import PDFProfileType


def test_deterministic_identifiers():
    raw = "test_sha256_hash_string_for_unit_tests"
    sha256 = hashlib.sha256(raw.encode("utf-8")).hexdigest()

    doc_id = generate_document_id(sha256)
    assert doc_id == f"doc_{sha256[:16]}"

    page_id = generate_page_id(doc_id, 1)
    assert page_id == f"{doc_id}_p0001"

    block_id = generate_block_id(page_id, 5)
    assert block_id == f"{doc_id}_p0001_b00005"

    table_id = generate_table_id(page_id, 2)
    assert table_id == f"{doc_id}_p0001_t002"

    cell_id = generate_cell_id(table_id, 1, 3)
    assert cell_id == f"{doc_id}_p0001_t002_r001_c003"


def test_document_ir_schema_construction():
    source_doc = SourceDocument(
        document_id="doc_1234567890abcdef",
        filename="test.pdf",
        path="/tmp/test.pdf",
        sha256="1234567890abcdef1234567890abcdef",
        page_count=1,
    )
    profile = DocumentProfile(
        pdf_profile=PDFProfileType.NATIVE_PDF,
        has_text_layer=True,
        text_character_count=100,
    )
    provenance = ParserProvenance(
        parser_id="pymupdf_native",
        parser_version="1.0.0",
    )
    geom = Geometry(
        bbox=[10.0, 20.0, 200.0, 100.0],
        page_width=595.0,
        page_height=842.0,
    )
    block = BlockIR(
        block_id="doc_1234567890abcdef_p0001_b00001",
        page_number=1,
        text="Sample Invoice Content",
        geometry=geom,
    )
    page = PageIR(
        page_id="doc_1234567890abcdef_p0001",
        page_number=1,
        width=595.0,
        height=842.0,
        blocks=[block],
        text_content="Sample Invoice Content",
    )
    doc_ir = DocumentIR(
        document_id="doc_1234567890abcdef",
        source_document=source_doc,
        profile=profile,
        provenance=provenance,
        pages=[page],
        full_text="Sample Invoice Content",
    )

    assert doc_ir.document_id == "doc_1234567890abcdef"
    assert len(doc_ir.pages) == 1
    assert doc_ir.pages[0].blocks[0].geometry.bbox == [10.0, 20.0, 200.0, 100.0]
