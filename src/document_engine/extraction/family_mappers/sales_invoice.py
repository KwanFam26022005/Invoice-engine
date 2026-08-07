"""Sales Invoice specialized family mapper."""

from typing import Dict, List, Tuple

from document_engine.extraction.evidence import (
    find_anchor_value,
    find_table_evidence,
    find_text_evidence,
    resolve_semantic_columns,
    semantic_columns_are_ambiguous,
)
from document_engine.extraction.normalizer import normalize_tax_id, parse_date, parse_decimal
from document_engine.ir.models import DocumentIR
from document_engine.schemas.family_schemas import (
    CommonDocumentFields,
    FieldCandidate,
    LineItem,
    Party,
    SalesInvoicePayload,
)


class SalesInvoiceMapper:
    def map(
        self, document_ir: DocumentIR
    ) -> Tuple[SalesInvoicePayload, Dict[str, FieldCandidate]]:
        field_candidates: Dict[str, FieldCandidate] = {}

        # 1. Document Number
        doc_num, doc_ev = find_anchor_value(
            document_ir,
            r"(?:số hóa đơn|so hoa don|invoice (?:no|number)|(?:^|\n)\s*(?:số|so)\s*:)",
            r"[A-Za-z0-9/\-]+",
        )
        if doc_num:
            field_candidates["document_number"] = FieldCandidate(
                value=doc_num, raw_value=doc_num, evidence_references=doc_ev
            )
            field_candidates["common.document_number"] = FieldCandidate(
                value=doc_num, raw_value=doc_num, evidence_references=doc_ev
            )

        # 2. Series
        series, _series_ev = find_text_evidence(
            document_ir, r"(?:ký hiệu|ky hieu|series)\s*:\s*([A-Za-z0-9\/\-]+)"
        )

        # 3. Date
        raw_date, date_ev = find_text_evidence(
            document_ir,
            r"(?:ngày|ngay|date)\s*:?\s*(\d{1,2}[\/\-\.]\d{1,2}[\/\-\.]\d{4}|\d{4}[\/\-\.]\d{1,2}[\/\-\.]\d{1,2}|\d{1,2}\s*tháng\s*\d{1,2}\s*năm\s*\d{4})",
        )
        norm_date = parse_date(raw_date)[0] if raw_date else None
        if norm_date:
            field_candidates["issue_date"] = FieldCandidate(
                value=norm_date, raw_value=raw_date, evidence_references=date_ev
            )
            field_candidates["common.issue_date"] = FieldCandidate(
                value=norm_date, raw_value=raw_date, evidence_references=date_ev
            )

        # 4. Seller & Buyer
        seller_tax, _seller_tax_ev = find_text_evidence(
            document_ir, r"(?:mst|mã số thuế|ma so thue)\s*(?:bán|bên bán|ben ban)?\s*:\s*([\d\-]+)"
        )
        buyer_tax, _buyer_tax_ev = find_text_evidence(
            document_ir, r"(?:mst|mã số thuế|ma so thue)\s*(?:mua|bên mua|ben mua)?\s*:\s*([\d\-]+)"
        )

        seller = Party(tax_id=normalize_tax_id(seller_tax)[0] if seller_tax else None)
        buyer = Party(tax_id=normalize_tax_id(buyer_tax)[0] if buyer_tax else None)
        seller_name, seller_name_ev = find_anchor_value(
            document_ir, r"(?:tên đơn vị bán hàng|đơn vị bán hàng|người bán)"
        )
        buyer_name, buyer_name_ev = find_anchor_value(
            document_ir, r"(?:tên đơn vị mua hàng|đơn vị mua hàng|người mua hàng)"
        )
        seller.name = seller_name
        buyer.name = buyer_name
        if seller_name:
            field_candidates["common.seller.name"] = FieldCandidate(value=seller_name, raw_value=seller_name, evidence_references=seller_name_ev)
        if buyer_name:
            field_candidates["common.buyer.name"] = FieldCandidate(value=buyer_name, raw_value=buyer_name, evidence_references=buyer_name_ev)

        # 5. Grand Total
        grand_raw, grand_ev = find_anchor_value(
            document_ir,
            r"(?:tổng tiền phải thanh toán|tong tien phai thanh toan|"
            r"tổng tiền thanh toán|tong tien thanh toan|tổng thanh toán|"
            r"tong thanh toan|tổng cộng|tong cong|grand total)",
            r"[\d., ]+(?:\s*(?:đ|vnd))?",
        )
        grand_total = parse_decimal(grand_raw)[0] if grand_raw else None
        if grand_total is not None:
            field_candidates["grand_total"] = FieldCandidate(
                value=str(grand_total), raw_value=grand_raw, evidence_references=grand_ev
            )
            field_candidates["common.grand_total"] = FieldCandidate(
                value=str(grand_total), raw_value=grand_raw, evidence_references=grand_ev
            )

        # 6. Line Items from TableIR
        line_items: List[LineItem] = []
        for page in document_ir.pages:
            for table in page.tables:
                if table.row_count > 1:
                    header_columns = resolve_semantic_columns(table)
                    if semantic_columns_are_ambiguous(table):
                        continue
                    rows_dict: Dict[int, Dict[int, str]] = {}
                    cells_obj: Dict[Tuple[int, int], any] = {}
                    for c in table.cells:
                        r_idx = getattr(c, "row_index", 0)
                        c_idx = getattr(c, "col_index", getattr(c, "column_index", 0))
                        rows_dict.setdefault(r_idx, {})[c_idx] = c.text
                        cells_obj[(r_idx, c_idx)] = c

                    for r_idx in sorted(rows_dict.keys()):
                        if r_idx == 0:
                            continue
                        r_data = rows_dict[r_idx]
                        texts = [r_data.get(col, "") for col in sorted(r_data.keys())]
                        if not any(texts):
                            continue

                        if header_columns:
                            desc = r_data.get(header_columns.get("description", -1), "")
                            unit = r_data.get(header_columns.get("unit", -1))
                            qty_dec = parse_decimal(r_data.get(header_columns.get("quantity", -1)))[0] if "quantity" in header_columns else None
                            price_dec = parse_decimal(r_data.get(header_columns.get("unit_price", -1)))[0] if "unit_price" in header_columns else None
                            amt_dec = parse_decimal(r_data.get(header_columns.get("amount", -1)))[0] if "amount" in header_columns else None
                        else:
                            desc, unit = (texts[0], texts[1]) if len(texts) >= 2 else ("", None)
                            qty_dec = parse_decimal(texts[2])[0] if len(texts) > 2 else None
                            price_dec = parse_decimal(texts[3])[0] if len(texts) > 3 else None
                            amt_dec = parse_decimal(texts[4])[0] if len(texts) > 4 else None

                        ev_list = []
                        for c_idx in sorted(r_data.keys()):
                            c_obj = cells_obj.get((r_idx, c_idx))
                            if c_obj:
                                ev_list.append(
                                    find_table_evidence(document_ir, c_obj, table, page.page_number)
                                )

                        line_items.append(
                            LineItem(
                                item_id=f"item_{r_idx}",
                                description=desc,
                                unit=unit,
                                quantity=qty_dec,
                                unit_price=price_dec,
                                amount=amt_dec or (qty_dec * price_dec if qty_dec and price_dec else None),
                                evidence=ev_list,
                            )
                        )

        common = CommonDocumentFields(
            document_number=doc_num,
            document_series=series,
            issue_date=norm_date,
            currency="VND",
            seller=seller,
            buyer=buyer,
            grand_total=grand_total,
        )

        payload = SalesInvoicePayload(common=common, line_items=line_items)
        return payload, field_candidates
