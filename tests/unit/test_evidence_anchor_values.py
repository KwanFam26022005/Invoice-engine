"""Regression tests for block-aware anchor-value provenance."""

from document_engine.core.models import PDFProfileType
from document_engine.extraction.evidence import find_anchor_value
from document_engine.ir.models import BlockIR, DocumentIR, DocumentProfile, Geometry, PageIR, ParserProvenance, SourceDocument


def _document(pages):
    return DocumentIR(
        document_id="doc-evidence",
        source_document=SourceDocument(document_id="doc-evidence", filename="synthetic.pdf", path="synthetic.pdf", sha256="hash", page_count=len(pages)),
        profile=DocumentProfile(pdf_profile=PDFProfileType.NATIVE_PDF, has_text_layer=True),
        provenance=ParserProvenance(parser_id="synthetic", parser_version="1"),
        pages=pages,
        full_text="\n".join(block.text for page in pages for block in page.blocks),
    )


def test_anchor_value_uses_same_block_provenance():
    block = BlockIR(block_id="a", page_number=1, text="Code: VALUE", geometry=Geometry(bbox=[1, 2, 3, 4]))
    value, evidence = find_anchor_value(_document([PageIR(page_id="p1", page_number=1, blocks=[block])]), r"code", r"[A-Z]+")
    assert value == "VALUE"
    assert evidence[0].block_id == "a"
    assert evidence[0].source_text == "VALUE"


def test_anchor_value_uses_value_block_and_never_crosses_pages():
    anchor = BlockIR(block_id="anchor", page_number=1, text="Code")
    value_block = BlockIR(block_id="value", page_number=1, text="VALUE", geometry=Geometry(bbox=[5, 6, 7, 8]))
    page1 = PageIR(page_id="p1", page_number=1, blocks=[anchor, BlockIR(block_id="empty", page_number=1, text=""), value_block])
    page2 = PageIR(page_id="p2", page_number=2, blocks=[BlockIR(block_id="other", page_number=2, text="OTHER")])
    value, evidence = find_anchor_value(_document([page1, page2]), r"code", r"[A-Z]+")
    assert value == "VALUE"
    assert evidence[0].block_id == "value"
    assert evidence[0].page_number == 1
    assert evidence[0].bbox == [5, 6, 7, 8]
    assert evidence[0].source_text == "VALUE"


def test_anchor_value_does_not_use_a_value_from_the_next_page():
    page1 = PageIR(
        page_id="p1",
        page_number=1,
        blocks=[BlockIR(block_id="anchor", page_number=1, text="Code")],
    )
    page2 = PageIR(
        page_id="p2",
        page_number=2,
        blocks=[BlockIR(block_id="other", page_number=2, text="VALUE")],
    )

    value, evidence = find_anchor_value(
        _document([page1, page2]), r"code", r"[A-Z]+"
    )

    assert value is None
    assert evidence == []
