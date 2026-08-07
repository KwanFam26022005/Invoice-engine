"""Sales Invoice specialized family mapper."""

from decimal import Decimal
import re
from typing import Dict, List, Tuple

from document_engine.extraction.evidence import find_table_evidence, find_text_evidence
from document_engine.extraction.normalizer import normalize_tax_id, parse_date, parse_decimal
from document_engine.ir.models import DocumentIR, EvidenceReference
from document_engine.schemas.family_schemas import (
    CommonDocumentFields,
    FieldCandidate,
    LineItem,
    Party,
    SalesInvoicePayload,
    TaxBreakdown,
)


class SalesInvoiceMapper:
    def map(
        self, document_ir: DocumentIR
    ) -> Tuple[SalesInvoicePayload, Dict[str, FieldCandidate]]:
        field_candidates: Dict[str, FieldCandidate] = {}

        # 1. Document Number
        doc_num, doc_ev = find_text_evidence(
            document_ir, r"(?:số|so|invoice no|no\.?)\s*:\s*([A-Za-z0-9\/\-]+)"
        )
        if doc_num:
            field_candidates["document_number"] = FieldCandidate(
                value=doc_num, raw_value=doc_num, evidence_references=doc_ev
            )

        # 2. Series
        series, series_ev = find_text_evidence(
            document_ir, r"(?:ký hiệu|ky hieu|series)\s*:\s*([A-Za-z0-9\/\-]+)"
        )

        # 3. Date
        raw_date, date_ev = find_text_evidence(
            document_ir,
            r"(?:ngày|ngay|date)\s*:?\s*(\d{1,2}[\/\-\.]\d{1,2}[\/\-\.]\d{4}|\d{4}[\/\-\.]\d{1,2}[\/\-\.]\d{1,2})",
        )
        norm_date = parse_date(raw_date)[0] if raw_date else None
        if norm_date:
            field_candidates["issue_date"] = FieldCandidate(
                value=norm_date, raw_value=raw_date, evidence_references=date_ev
            )

        # 4. Seller & Buyer
        seller_tax, seller_tax_ev = find_text_evidence(
            document_ir, r"(?:mst|mã số thuế)\s*(?:bán|bên bán)?\s*:\s*([\d\-]+)"
        )
        buyer_tax, buyer_tax_ev = find_text_evidence(
            document_ir, r"(?:mst|mã số thuế)\s*(?:mua|bên mua)?\s*:\s*([\d\-]+)"
        )

        seller = Party(tax_id=normalize_tax_id(seller_tax)[0] if seller_tax else None)
        buyer = Party(tax_id=normalize_tax_id(buyer_tax)[0] if buyer_tax else None)

        # 5. Grand Total
        grand_raw, grand_ev = find_text_evidence(
            document_ir,
            r"(?:tổng cộng|tong cong|total|tổng tiền thanh toán)\s*:\s*([\d\.,\s]+)",
        )
        grand_total = parse_decimal(grand_raw)[0] if grand_raw else None
        if grand_total is not None:
            field_candidates["grand_total"] = FieldCandidate(
                value=str(grand_total), raw_value=grand_raw, evidence_references=grand_ev
            )

        # 6. Line Items from TableIR
        line_items: List[LineItem] = []
        for page in document_ir.pages:
            for table in page.tables:
                if table.row_count > 1:
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

                        desc = texts[0] if len(texts) > 0 else ""
                        unit = texts[1] if len(texts) > 1 else None
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
