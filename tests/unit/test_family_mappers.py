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
from document_engine.extraction.family_mappers.sales_invoice import SalesInvoiceMapper
from document_engine.extraction.family_mappers.tax_withholding import TaxWithholdingMapper
from document_engine.extraction.family_mappers.utility_consumption import (
    UtilityConsumptionMapper,
)
from document_engine.schemas.family_schemas import MeterReading, TaxWithholdingCertificatePayload


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


def test_tax_mapper_extracts_colon_certificate_number_with_evidence():
    source = SourceDocument(document_id="doc_tax_number", path="synthetic.pdf", filename="synthetic.pdf", sha256="hash", page_count=1)
    profile = DocumentProfile(pdf_profile=PDFProfileType.NATIVE_PDF, has_text_layer=True)
    block = BlockIR(block_id="value", page_number=1, text="So: CERT-SYNTH-001")
    document = DocumentIR(document_id="doc_tax_number", source_document=source, profile=profile, provenance=ParserProvenance(parser_id="synthetic", parser_version="1"), pages=[PageIR(page_id="p", page_number=1, blocks=[block])], full_text=block.text)

    payload, candidates = TaxWithholdingMapper().map(document)

    assert payload.certificate_number == "CERT-SYNTH-001"
    assert payload.common.document_number == "CERT-SYNTH-001"
    assert candidates["certificate_number"].evidence_references


def test_tax_mapper_extracts_next_block_certificate_number_with_value_evidence():
    source = SourceDocument(document_id="doc_tax_next", path="synthetic.pdf", filename="synthetic.pdf", sha256="hash", page_count=1)
    profile = DocumentProfile(pdf_profile=PDFProfileType.NATIVE_PDF, has_text_layer=True)
    label = BlockIR(block_id="label", page_number=1, text="Số (No):")
    value = BlockIR(block_id="number", page_number=1, text="CERT-NEXT-001")
    document = DocumentIR(document_id="doc_tax_next", source_document=source, profile=profile, provenance=ParserProvenance(parser_id="synthetic", parser_version="1"), pages=[PageIR(page_id="p", page_number=1, blocks=[label, value])], full_text="Số (No):\nCERT-NEXT-001")

    payload, candidates = TaxWithholdingMapper().map(document)

    assert payload.certificate_number == "CERT-NEXT-001"
    assert candidates["certificate_number"].evidence_references[0].block_id == "number"


def test_tax_mapper_extracts_complete_synthetic_acceptance_fields():
    values = [
        ("form-label", "Mẫu số:"), ("form", "01/FAKE"),
        ("serial-label", "Ký hiệu:"), ("serial", "AA/26E"),
        ("cert-label", "Số (No):"), ("cert", "CERT-FAKE-001"),
        ("payer-label", "[01] Tên tổ chức trả thu nhập"),
        ("payer", "Fictional Payer LLC"),
        ("payer-tax-label", "[02] Mã số thuế"),
        ("payer-tax", "0101234567"),
        ("recipient-label", "[05] Họ và tên"), ("recipient", "Fictional Recipient"),
        ("recipient-tax-label", "[06] Mã số thuế"),
        ("recipient-tax", "0107654321"),
        ("period", "Từ tháng 2 đến tháng 5 năm 2026"),
        ("taxable", "Tổng thu nhập chịu thuế: 1000 đ"),
        ("calculation", "Tổng thu nhập tính thuế: 900 đ"),
        ("withheld", "Số thuế đã khấu trừ: 90 đ"),
        ("date-label", "Ngày (date)"),
        ("date", "07 tháng (month) 08 năm (year) 2026"),
        ("lookup-label", "Mã tra cứu:"), ("lookup", "LOOKUP-FAKE"),
    ]
    blocks = [BlockIR(block_id=block_id, page_number=1, text=text) for block_id, text in values]
    document = _document_for_mapper("doc-tax-complete", blocks)

    payload, candidates = TaxWithholdingMapper().map(document)

    assert payload.form_number == "01/FAKE"
    assert payload.serial_number == "AA/26E"
    assert payload.certificate_number == "CERT-FAKE-001"
    assert payload.common.document_number == "CERT-FAKE-001"
    assert payload.income_paying_organization.name == "Fictional Payer LLC"
    assert payload.income_paying_organization.tax_id == "0101234567"
    assert payload.recipient.name == "Fictional Recipient"
    assert payload.recipient.tax_id == "0107654321"
    assert payload.payment_period == "2026-02/2026-05"
    assert payload.total_taxable_income == Decimal(1000)
    assert payload.total_tax_calculation_income == Decimal(900)
    assert payload.withheld_tax == Decimal(90)
    assert payload.signature_date == "2026-08-07"
    assert payload.lookup_code == "LOOKUP-FAKE"
    for key in (
            "form_number", "serial_number", "certificate_number",
            "income_paying_organization.name", "income_paying_organization.tax_id",
            "recipient.name", "recipient.tax_id", "payment_period",
        "total_taxable_income", "total_tax_calculation_income", "withheld_tax",
        "signature_date", "lookup_code",
    ):
        assert candidates[key].evidence_references


def test_sales_mapper_uses_semantic_headers_with_leading_code_columns():
    headers = ["STT", "Mã hàng", "Tên hàng hóa", "ĐVT", "Số lượng", "Đơn giá", "Thành tiền"]
    row = ["1", "SKU-1", "Dịch vụ giả lập", "gói", "2", "500", "1000"]
    cells = [
        TableCellIR(cell_id=f"h{index}", row_index=0, col_index=index, text=text)
        for index, text in enumerate(headers)
    ] + [
        TableCellIR(cell_id=f"r{index}", row_index=1, col_index=index, text=text)
        for index, text in enumerate(row)
    ]
    table = TableIR(table_id="sales-semantic", page_number=1, row_count=2, col_count=7, cells=cells)
    document = _document_for_mapper("doc-sales-semantic", [], [table])

    payload, _ = SalesInvoiceMapper().map(document)

    assert payload.line_items[0].description == "Dịch vụ giả lập"
    assert payload.line_items[0].unit == "gói"
    assert payload.line_items[0].quantity == Decimal(2)
    assert payload.line_items[0].unit_price == Decimal(500)
    assert payload.line_items[0].amount == Decimal(1000)


def test_sales_mapper_extracts_party_names_and_vietnamese_issue_date():
    block = BlockIR(
        block_id="sales-fields",
        page_number=1,
        text=(
            "Đơn vị bán hàng: Fictional Seller\n"
            "Người mua hàng: Fictional Buyer\n"
            "Ngày 7 tháng 8 năm 2026"
        ),
    )

    payload, candidates = SalesInvoiceMapper().map(
        _document_for_mapper("doc-sales-fields", [block])
    )

    assert payload.common.seller.name == "Fictional Seller"
    assert payload.common.buyer.name == "Fictional Buyer"
    assert payload.common.issue_date == "2026-08-07"
    assert candidates["common.seller.name"].evidence_references
    assert candidates["common.buyer.name"].evidence_references


def test_utility_mapper_uses_semantic_headers_without_positional_shift():
    headers = ["Mã", "Mô tả dịch vụ", "Đơn vị", "Số lượng", "Đơn giá", "Thành tiền"]
    row = ["T1", "Nước sinh hoạt", "m3", "3", "100", "300"]
    cells = [
        TableCellIR(cell_id=f"h{index}", row_index=0, col_index=index, text=text)
        for index, text in enumerate(headers)
    ] + [
        TableCellIR(cell_id=f"r{index}", row_index=1, col_index=index, text=text)
        for index, text in enumerate(row)
    ]
    table = TableIR(table_id="utility-semantic", page_number=1, row_count=2, col_count=6, cells=cells)
    document = _document_for_mapper("doc-utility-semantic", [], [table])

    payload, _ = UtilityConsumptionMapper().map(document)

    assert payload.pricing_tiers[0].tier_name == "Nước sinh hoạt"
    assert payload.pricing_tiers[0].quantity == Decimal(3)
    assert payload.pricing_tiers[0].unit_price == Decimal(100)
    assert payload.pricing_tiers[0].amount == Decimal(300)


def test_utility_mapper_extracts_document_number_and_vietnamese_issue_date():
    block = BlockIR(
        block_id="utility-fields",
        page_number=1,
        text="Số hóa đơn: UTILITY-FAKE-001\nNgày 7 tháng 8 năm 2026",
    )

    payload, candidates = UtilityConsumptionMapper().map(
        _document_for_mapper("doc-utility-fields", [block])
    )

    assert payload.common.document_number == "UTILITY-FAKE-001"
    assert payload.common.issue_date == "2026-08-07"
    assert candidates["common.document_number"].evidence_references
    assert candidates["common.issue_date"].evidence_references


def _document_for_mapper(document_id, blocks, tables=None):
    source = SourceDocument(
        document_id=document_id,
        path="synthetic.pdf",
        filename="synthetic.pdf",
        sha256="hash",
        page_count=1,
    )
    page = PageIR(page_id="p", page_number=1, blocks=blocks, tables=tables or [])
    return DocumentIR(
        document_id=document_id,
        source_document=source,
        profile=DocumentProfile(pdf_profile=PDFProfileType.NATIVE_PDF, has_text_layer=True),
        provenance=ParserProvenance(parser_id="synthetic", parser_version="1"),
        pages=[page],
        full_text="\n".join(block.text for block in blocks),
    )
