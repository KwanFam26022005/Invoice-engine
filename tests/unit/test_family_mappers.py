"""Unit tests for evidence-backed family mappers, missing vs zero, and completeness."""

from decimal import Decimal
from document_engine.core.models import DocumentFamilyType, PDFProfileType
from document_engine.extraction.mapper import DocumentMapper
from document_engine.ir.models import (
    BlockIR,
    DocumentIR,
    DocumentProfile,
    PageIR,
    ParserProvenance,
    SourceDocument,
    TableCellIR,
    TableIR,
)
from document_engine.schemas.family_schemas import MeterReading, TaxWithholdingCertificatePayload
from document_engine.extraction.family_mappers.tax_withholding import TaxWithholdingMapper


def test_missing_vs_zero_defaults():
    meter = MeterReading()
    assert meter.opening_reading is None
    assert meter.closing_reading is None
    assert meter.consumption is None

    tax_payload = TaxWithholdingCertificatePayload()
    assert tax_payload.withheld_tax is None
    assert tax_payload.total_taxable_income is None


def test_sales_invoice_family_mapper():
    source = SourceDocument(
        document_id="doc_sales_01",
        path="fake.pdf",
        filename="fake.pdf",
        sha256="1234567890abcdef",
        page_count=1,
    )
    profile = DocumentProfile(
        pdf_profile=PDFProfileType.NATIVE_PDF,
        has_text_layer=True,
        text_character_count=200,
    )
    prov = ParserProvenance(parser_id="pymupdf_native", parser_version="1.0.0")

    cell_1 = TableCellIR(cell_id="c1", row_index=0, col_index=0, text="Mặt hàng")
    cell_2 = TableCellIR(cell_id="c2", row_index=0, col_index=1, text="ĐVT")
    cell_3 = TableCellIR(cell_id="c3", row_index=0, col_index=2, text="Số lượng")
    cell_4 = TableCellIR(cell_id="c4", row_index=0, col_index=3, text="Đơn giá")
    cell_5 = TableCellIR(cell_id="c5", row_index=0, col_index=4, text="Thành tiền")

    cell_6 = TableCellIR(cell_id="c6", row_index=1, col_index=0, text="Dịch vụ IT")
    cell_7 = TableCellIR(cell_id="c7", row_index=1, col_index=1, text="Gói")
    cell_8 = TableCellIR(cell_id="c8", row_index=1, col_index=2, text="2")
    cell_9 = TableCellIR(cell_id="c9", row_index=1, col_index=3, text="5000000")
    cell_10 = TableCellIR(cell_id="c10", row_index=1, col_index=4, text="10000000")

    table = TableIR(table_id="t1", page_number=1, row_count=2, col_count=5, cells=[cell_1, cell_2, cell_3, cell_4, cell_5, cell_6, cell_7, cell_8, cell_9, cell_10])

    b1 = BlockIR(block_id="b1", page_number=1, text="HÓA ĐƠN GIÁ TRỊ GIA TĂNG\nSố: INV-2026-001\nNgày: 07/08/2026\nMã số thuế bán: 010999888\nMã số thuế mua: 010111222\nTổng cộng: 10.000.000")

    page = PageIR(page_id="p1", page_number=1, width=595.0, height=842.0, blocks=[b1], tables=[table], text_content=b1.text)

    doc_ir = DocumentIR(
        document_id="doc_sales_01",
        source_document=source,
        profile=profile,
        provenance=prov,
        pages=[page],
        full_text=b1.text,
    )

    mapper = DocumentMapper()
    class_res = type("ClassificationResult", (), {"document_family": DocumentFamilyType.SALES_INVOICE})()
    envelope = mapper.map_to_envelope(doc_ir, class_res)

    assert envelope.payload.common.document_number == "INV-2026-001"
    assert envelope.payload.common.seller.tax_id == "010999888"
    assert envelope.payload.common.buyer.tax_id == "010111222"
    assert envelope.payload.common.grand_total == Decimal(10000000)
    assert len(envelope.payload.line_items) == 1
    assert envelope.payload.line_items[0].description == "Dịch vụ IT"
    assert envelope.payload.line_items[0].amount == Decimal(10000000)

    comp = mapper.evaluate_completeness(envelope, doc_ir)
    assert comp.completeness_score == 1.0
    assert comp.requires_review is False


def test_tax_mapper_keeps_calculation_income_zero_distinct_from_taxable_income():
    source = SourceDocument(document_id="doc_tax", path="fake.pdf", filename="fake.pdf", sha256="hash", page_count=1)
    profile = DocumentProfile(pdf_profile=PDFProfileType.NATIVE_PDF, has_text_layer=True)
    block = BlockIR(block_id="b", page_number=1, text="""Mẫu số:\n01/ABC
Ký hiệu:\nAA/26E
Số (No):\nCERT-1
Tổng thu nhập chịu thuế: 1000
Tổng thu nhập tính thuế: 0
Số thuế đã khấu trừ: 100
Ngày (date) 07 tháng 08 năm 2026
Mã tra cứu: LOOKUP-X""")
    document = DocumentIR(document_id="doc_tax", source_document=source, profile=profile, provenance=ParserProvenance(parser_id="synthetic", parser_version="1"), pages=[PageIR(page_id="p", page_number=1, blocks=[block])], full_text=block.text)

    payload, candidates = TaxWithholdingMapper().map(document)

    assert payload.form_number == "01/ABC"
    assert payload.total_taxable_income == Decimal(1000)
    assert payload.total_tax_calculation_income == Decimal(0)
    assert payload.lookup_code == "LOOKUP-X"
    assert candidates["form_number"].evidence_references
