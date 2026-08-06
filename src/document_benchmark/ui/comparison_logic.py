"""Pure logic functions for text, field, table, geometry, and metric comparisons."""

from __future__ import annotations

import difflib
from html.parser import HTMLParser
import re
import unicodedata
from decimal import Decimal
from typing import Any

from document_benchmark.ui.comparison_models import (
    BoundingBox,
    EngineView,
    FieldComparisonItem,
    PageGeometry,
    TableComparisonItem,
)


def normalize_text_unicode(text: str) -> str:
    """Normalize text using Unicode NFKC."""
    if not text:
        return ""
    return unicodedata.normalize("NFKC", text)


def normalize_whitespace(text: str) -> str:
    """Normalize multiple whitespaces into a single space and strip."""
    if not text:
        return ""
    return re.sub(r"\s+", " ", text).strip()


def remove_vietnamese_diacritics(text: str) -> str:
    """Remove Vietnamese accents/diacritics for diacritic-insensitive comparison."""
    if not text:
        return ""
    text = unicodedata.normalize("NFD", text)
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    text = text.replace("đ", "d").replace("Đ", "D")
    return unicodedata.normalize("NFC", text)


def compute_text_similarity(text1: str, text2: str, ignore_diacritics: bool = False) -> float:
    """Compute text similarity ratio using difflib.SequenceMatcher."""
    t1 = normalize_whitespace(normalize_text_unicode(text1))
    t2 = normalize_whitespace(normalize_text_unicode(text2))

    if ignore_diacritics:
        t1 = remove_vietnamese_diacritics(t1)
        t2 = remove_vietnamese_diacritics(t2)

    if not t1 and not t2:
        return 1.0
    if not t1 or not t2:
        return 0.0

    return round(difflib.SequenceMatcher(None, t1, t2).ratio(), 4)


def generate_unified_diff(
    text1: str,
    text2: str,
    label1: str = "Docling",
    label2: str = "PP-StructureV3",
) -> str:
    """Generate a unified diff string between two text blobs."""
    lines1 = normalize_text_unicode(text1).splitlines()
    lines2 = normalize_text_unicode(text2).splitlines()
    diff = difflib.unified_diff(
        lines1,
        lines2,
        fromfile=label1,
        tofile=label2,
        lineterm="",
    )
    return "\n".join(diff)


def normalize_tax_id_for_comparison(val: Any) -> str:
    """Normalize tax ID by extracting digits and hyphens."""
    if val is None:
        return ""
    s = str(val).strip()
    digits = re.sub(r"[^\d\-]", "", s)
    return digits.replace("-", "").strip()


def normalize_invoice_num_for_comparison(val: Any) -> str:
    """Normalize invoice number or series by uppercase and whitespace strip."""
    if val is None:
        return ""
    return re.sub(r"\s+", "", str(val)).upper().strip()


def normalize_amount_for_comparison(val: Any) -> str:
    """Normalize numeric amount by stripping presentation separators."""
    if val is None:
        return ""
    s = str(val).strip()
    clean = re.sub(r"[^\d.,\-]", "", s)
    if not clean:
        return ""
    try:
        if "," in clean and "." in clean:
            if clean.find(".") < clean.find(","):
                clean = clean.replace(".", "").replace(",", ".")
            else:
                clean = clean.replace(",", "")
        elif clean.count(".") > 1:
            clean = clean.replace(".", "")
        elif "," in clean:
            parts = clean.split(",")
            if len(parts[-1]) == 2:
                clean = clean.replace(",", ".")
            else:
                clean = clean.replace(",", "")
        dec = Decimal(clean)
        return f"{dec:.2f}"
    except Exception:
        return clean


def normalize_field_value(field_name: str, val: Any) -> str:
    """Normalize a field value based on field type conventions."""
    if val is None or val == "":
        return ""
    name_lower = field_name.lower()
    if "tax" in name_lower or "mst" in name_lower:
        return normalize_tax_id_for_comparison(val)
    if "invoice" in name_lower or "number" in name_lower or "series" in name_lower or "num" in name_lower:
        return normalize_invoice_num_for_comparison(val)
    if "amount" in name_lower or "total" in name_lower or "price" in name_lower or "vat" in name_lower or "subtotal" in name_lower:
        return normalize_amount_for_comparison(val)

    s = normalize_whitespace(normalize_text_unicode(str(val)))
    return s


def compare_fields(
    docling_cands: dict[str, Any],
    pp_cands: dict[str, Any],
    ignore_diacritics: bool = False,
) -> list[FieldComparisonItem]:
    """Compare union of field candidates between Docling and PP-StructureV3."""
    all_keys = sorted(set(docling_cands.keys()) | set(pp_cands.keys()))
    items: list[FieldComparisonItem] = []

    for k in all_keys:
        has_doc = k in docling_cands
        has_pp = k in pp_cands

        doc_raw = docling_cands.get(k) if has_doc else None
        pp_raw = pp_cands.get(k) if has_pp else None

        doc_norm = normalize_field_value(k, doc_raw) if has_doc else ""
        pp_norm = normalize_field_value(k, pp_raw) if has_pp else ""

        if ignore_diacritics:
            c_doc = remove_vietnamese_diacritics(doc_norm)
            c_pp = remove_vietnamese_diacritics(pp_norm)
        else:
            c_doc = doc_norm
            c_pp = pp_norm

        requires_check = False
        warning = None

        if not has_doc and not has_pp:
            status = "Không có dữ liệu"
            color = "gray"
            evidence = "Cả hai engine không trích xuất được trường này."
        elif has_doc and not has_pp:
            status = "Chỉ có ở Docling"
            color = "blue"
            evidence = f"Docling trích xuất: '{doc_raw}'"
        elif not has_doc and has_pp:
            status = "Chỉ có ở PP-StructureV3"
            color = "purple"
            evidence = f"PP-StructureV3 trích xuất: '{pp_raw}'"
        elif str(doc_raw).strip() == str(pp_raw).strip():
            status = "Đồng thuận hoàn toàn"
            color = "green"
            evidence = "Raw output hai engine hoàn toàn giống nhau."
        elif c_doc and c_pp and c_doc == c_pp:
            status = "Đồng thuận sau chuẩn hóa"
            color = "lightgreen"
            evidence = f"Đồng thuận sau khi chuẩn hóa ('{doc_norm}')."
        else:
            status = "Khác biệt"
            color = "orange"
            evidence = f"Docling: '{doc_raw}' vs PP-StructureV3: '{pp_raw}'"
            requires_check = True
            warning = "Giá trị trích xuất có sự khác biệt. Cần kiểm tra thủ công với PDF gốc."

        items.append(
            FieldComparisonItem(
                field_name=k,
                docling_raw=doc_raw,
                pp_raw=pp_raw,
                docling_normalized=doc_norm if has_doc else None,
                pp_normalized=pp_norm if has_pp else None,
                status=status,
                status_badge_color=color,
                evidence=evidence,
                requires_manual_check=requires_check,
                validation_warning=warning,
            )
        )

    return items


class SimpleHTMLTableParser(HTMLParser):
    """Safe HTML parser for extracting tables from PP-StructureV3 pred_html."""

    def __init__(self) -> None:
        super().__init__()
        self.rows: list[list[str]] = []
        self.current_row: list[str] = []
        self.current_cell: list[str] = []
        self.in_cell = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() in ("td", "th"):
            self.in_cell = True
            self.current_cell = []
        elif tag.lower() == "tr":
            self.current_row = []

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in ("td", "th"):
            self.in_cell = False
            self.current_row.append("".join(self.current_cell).strip())
        elif tag.lower() == "tr":
            if self.current_row:
                self.rows.append(self.current_row)

    def handle_data(self, data: str) -> None:
        if self.in_cell:
            self.current_cell.append(data)


def parse_html_table_safely(html_str: str) -> list[list[str]]:
    """Parse HTML table string safely using SimpleHTMLTableParser without unsafe HTML execution."""
    if not html_str or "<table" not in html_str.lower():
        return []
    try:
        parser = SimpleHTMLTableParser()
        parser.feed(html_str)
        return parser.rows
    except Exception:
        # Fallback regex parsing
        rows = []
        for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", html_str, re.DOTALL | re.IGNORECASE):
            cells = [
                re.sub(r"<[^>]+>", "", cell).strip()
                for cell in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", tr, re.DOTALL | re.IGNORECASE)
            ]
            if cells:
                rows.append(cells)
        return rows


def compare_tables(
    docling_tables: list[dict[str, Any]],
    pp_tables: list[dict[str, Any]],
) -> list[TableComparisonItem]:
    """Compare extracted tables between Docling and PP-StructureV3."""
    max_count = max(len(docling_tables), len(pp_tables))
    items: list[TableComparisonItem] = []

    for idx in range(max_count):
        doc_tbl = docling_tables[idx] if idx < len(docling_tables) else None
        pp_tbl = pp_tables[idx] if idx < len(pp_tables) else None

        d_headers: list[str] = []
        d_rows: list[list[Any]] = []
        d_row_cnt = 0
        d_col_cnt = 0

        if doc_tbl:
            d_headers = doc_tbl.get("headers", []) or []
            d_rows = doc_tbl.get("rows", []) or []
            d_row_cnt = len(d_rows)
            d_col_cnt = max(len(d_headers), max((len(r) for r in d_rows), default=0))

        pp_html_str: str | None = None
        pp_headers: list[str] = []
        pp_rows: list[list[Any]] = []
        pp_cell_boxes = 0
        pp_row_cnt = 0
        pp_col_cnt = 0

        if pp_tbl:
            raw = pp_tbl.get("raw", {}) or {}
            pp_html_str = raw.get("pred_html")
            cell_boxes = raw.get("cell_box_list", []) or []
            pp_cell_boxes = len(cell_boxes)

            if pp_html_str:
                parsed_grid = parse_html_table_safely(pp_html_str)
                if parsed_grid:
                    pp_headers = parsed_grid[0]
                    pp_rows = parsed_grid[1:] if len(parsed_grid) > 1 else []
                    pp_row_cnt = len(parsed_grid)
                    pp_col_cnt = max((len(r) for r in parsed_grid), default=0)

        # Calculate structural similarity
        if d_row_cnt == pp_row_cnt and d_col_cnt == pp_col_cnt and (d_row_cnt > 0):
            sim_score = 1.0
            status = "Cùng kích thước bảng"
        elif abs(d_row_cnt - pp_row_cnt) <= 2 and (d_col_cnt == pp_col_cnt or d_col_cnt == 0 or pp_col_cnt == 0):
            sim_score = 0.75
            status = "Kích thước tương tự"
        elif doc_tbl and pp_tbl:
            sim_score = 0.5
            status = "Khác kích thước dòng/cột"
        elif doc_tbl:
            sim_score = 0.0
            status = "Chỉ có ở Docling"
        else:
            sim_score = 0.0
            status = "Chỉ có ở PP-StructureV3"

        pg_num = (doc_tbl.get("page_number", 1) if doc_tbl else pp_tbl.get("page_number", 1)) if (doc_tbl or pp_tbl) else 1

        items.append(
            TableComparisonItem(
                table_index=idx,
                page_number=pg_num,
                docling_headers=d_headers,
                docling_rows=d_rows,
                pp_pred_html=pp_html_str,
                pp_parsed_headers=pp_headers,
                pp_parsed_rows=pp_rows,
                pp_cell_box_count=pp_cell_boxes,
                docling_row_count=d_row_cnt,
                docling_col_count=d_col_cnt,
                pp_row_count=pp_row_cnt,
                pp_col_count=pp_col_cnt,
                structural_similarity_score=sim_score,
                structural_status=status,
            )
        )

    return items


def extract_page_geometry_from_engine(engine_view: EngineView | None) -> dict[int, PageGeometry]:
    """Extract bounding box geometry per page from engine raw payload."""
    geometries: dict[int, PageGeometry] = {}
    if not engine_view or not engine_view.raw_payload:
        return geometries

    payload = engine_view.raw_payload

    # PP-StructureV3 format
    page_results = payload.get("page_results", [])
    if page_results:
        for p_res in page_results:
            res_dict = p_res.get("res", {}) if isinstance(p_res, dict) else {}
            pg_num = int(res_dict.get("page_index", 0)) + 1
            w = float(res_dict.get("width", 1.0) or 1.0)
            h = float(res_dict.get("height", 1.0) or 1.0)

            boxes: list[BoundingBox] = []

            # Layout boxes
            layout_det = res_dict.get("layout_det_res", {}) or {}
            for l_box in layout_det.get("boxes", []) or []:
                coord = l_box.get("coordinate", [])
                if len(coord) == 4:
                    boxes.append(
                        BoundingBox(
                            label=str(l_box.get("label", "layout")),
                            box=[float(x) for x in coord],
                            score=float(l_box["score"]) if "score" in l_box else None,
                            box_type="layout",
                            source_engine="ppstructure_v3",
                        )
                    )

            # OCR text boxes
            ocr_det = res_dict.get("overall_ocr_res", {}) or {}
            rec_boxes = ocr_det.get("rec_boxes", []) or []
            rec_texts = ocr_det.get("rec_texts", []) or []
            rec_scores = ocr_det.get("rec_scores", []) or []

            for idx_b, b_coord in enumerate(rec_boxes):
                if len(b_coord) == 4:
                    txt = rec_texts[idx_b] if idx_b < len(rec_texts) else ""
                    sc = float(rec_scores[idx_b]) if idx_b < len(rec_scores) else None
                    boxes.append(
                        BoundingBox(
                            label=txt[:30] if txt else "text",
                            box=[float(x) for x in b_coord],
                            score=sc,
                            box_type="text",
                            source_engine="ppstructure_v3",
                        )
                    )

            geometries[pg_num] = PageGeometry(
                page_number=pg_num,
                width=w,
                height=h,
                boxes=boxes,
                coordinate_system_valid=True,
            )

    return geometries


def build_selected_document_comparison(
    docling_view: EngineView | None,
    pp_view: EngineView | None,
    ignore_diacritics: bool = False,
) -> tuple[float, list[FieldComparisonItem], list[TableComparisonItem], float | None]:
    """Build similarity, field comparison, table comparison, and speed ratio."""
    doc_text = docling_view.full_text if docling_view else ""
    pp_text = pp_view.full_text if pp_view else ""

    sim_ratio = compute_text_similarity(doc_text, pp_text, ignore_diacritics=ignore_diacritics)

    doc_cands = docling_view.field_candidates if docling_view else {}
    pp_cands = pp_view.field_candidates if pp_view else {}
    field_items = compare_fields(doc_cands, pp_cands, ignore_diacritics=ignore_diacritics)

    doc_tables = docling_view.raw_payload.get("tables", []) if docling_view and docling_view.raw_payload else []
    pp_tables = pp_view.raw_payload.get("tables", []) if pp_view and pp_view.raw_payload else []
    table_items = compare_tables(doc_tables, pp_tables)

    speed_ratio: float | None = None
    if docling_view and pp_view:
        d_mean = docling_view.performance_stats.extract_ms_mean
        p_mean = pp_view.performance_stats.extract_ms_mean
        if d_mean > 0 and p_mean > 0:
            speed_ratio = round(d_mean / p_mean, 2)

    return sim_ratio, field_items, table_items, speed_ratio
