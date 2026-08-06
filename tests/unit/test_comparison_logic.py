"""Unit tests for comparison_logic module."""

from document_benchmark.ui.comparison_logic import (
    compare_fields,
    compare_tables,
    compute_text_similarity,
    normalize_amount_for_comparison,
    normalize_invoice_num_for_comparison,
    normalize_tax_id_for_comparison,
    parse_html_table_safely,
    remove_vietnamese_diacritics,
)


def test_text_similarity_identical() -> None:
    t1 = "HÓA ĐƠN GIÁ TRỊ GIA TĂNG"
    t2 = "HÓA ĐƠN GIÁ TRỊ GIA TĂNG"
    assert compute_text_similarity(t1, t2) == 1.0


def test_text_similarity_different() -> None:
    t1 = "CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM"
    t2 = "BIÊN LAI THU TIỀN PHÍ LỆ PHÍ"
    sim = compute_text_similarity(t1, t2)
    assert 0.0 <= sim < 0.5


def test_remove_vietnamese_diacritics() -> None:
    raw = "Hóa đơn điện tử Nguyễn Văn A"
    cleaned = remove_vietnamese_diacritics(raw)
    assert cleaned == "Hoa don dien tu Nguyen Van A"


def test_normalizers() -> None:
    assert normalize_tax_id_for_comparison("0101234567-001") == "0101234567001"
    assert normalize_invoice_num_for_comparison("bk/18e 000503") == "BK/18E000503"
    assert normalize_amount_for_comparison("18.500.000 VNĐ") == "18500000.00"


def test_compare_fields_union_and_status() -> None:
    doc_cands = {
        "invoice_number": "000503",
        "invoice_series": "BK/18E",
        "seller_tax_id": "0101234567",
    }
    pp_cands = {
        "invoice_number": "000503",
        "seller_tax_id": "0101234567-000",
        "total_amount": "18.500.000",
    }

    items = compare_fields(doc_cands, pp_cands)
    field_map = {item.field_name: item for item in items}

    assert "invoice_number" in field_map
    assert field_map["invoice_number"].status == "Đồng thuận hoàn toàn"

    assert "invoice_series" in field_map
    assert field_map["invoice_series"].status == "Chỉ có ở Docling"

    assert "total_amount" in field_map
    assert field_map["total_amount"].status == "Chỉ có ở PP-StructureV3"

    assert "seller_tax_id" in field_map
    assert field_map["seller_tax_id"].status in ("Khác biệt", "Đồng thuận sau chuẩn hóa")


def test_parse_html_table_safely() -> None:
    html_sample = """
    <table>
        <tr><th>STT</th><th>Tên hàng hóa</th><th>Thành tiền</th></tr>
        <tr><td>1</td><td>Sản phẩm A</td><td>100,000</td></tr>
    </table>
    """
    rows = parse_html_table_safely(html_sample)
    assert len(rows) == 2
    assert rows[0] == ["STT", "Tên hàng hóa", "Thành tiền"]
    assert rows[1] == ["1", "Sản phẩm A", "100,000"]


def test_compare_tables() -> None:
    doc_tables = [
        {"headers": ["Col1", "Col2"], "rows": [["1", "2"]], "page_number": 1}
    ]
    pp_tables = [
        {"raw": {"pred_html": "<table><tr><th>Col1</th><th>Col2</th></tr><tr><td>1</td><td>2</td></tr></table>"}, "page_number": 1}
    ]

    items = compare_tables(doc_tables, pp_tables)
    assert len(items) == 1
    assert items[0].docling_row_count == 1
    assert items[0].pp_row_count == 2
