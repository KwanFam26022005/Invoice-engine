"""Field mapper mapping raw extracted fields and text heuristics to canonical schemas."""

from typing import Tuple

from document_benchmark.core.statuses import DocumentFamily, DocumentSubtype


def detect_document_family(text: str) -> Tuple[DocumentFamily, DocumentSubtype]:
    """Classify document family and subtype from full text heuristics."""
    if not text:
        return DocumentFamily.UNKNOWN, DocumentSubtype.UNKNOWN

    txt_upper = text.upper()

    if "HÓA ĐƠN" in txt_upper or "HOA DON" in txt_upper or "INVOICE" in txt_upper:
        if "VIỄN THÔNG" in txt_upper or "INTERNET" in txt_upper or "ĐIỆN" in txt_upper or "NƯỚC" in txt_upper:
            return DocumentFamily.INVOICE, DocumentSubtype.UTILITY_INVOICE
        elif "LOGISTICS" in txt_upper or "VẬN TẢI" in txt_upper or "CẢNG" in txt_upper or "NHIÊN LIỆU" in txt_upper:
            return DocumentFamily.INVOICE, DocumentSubtype.LOGISTICS_INVOICE
        return DocumentFamily.INVOICE, DocumentSubtype.E_INVOICE

    if "PHIẾU ĐỀ NGHỊ" in txt_upper or "ĐỀ XUẤT VĂN PHÒNG PHẨM" in txt_upper or "VĂN PHÒNG PHẨM" in txt_upper:
        return DocumentFamily.OFFICE_SUPPLY_REQUEST, DocumentSubtype.OFFICE_SUPPLY_REQUEST

    if "TỜ TRÌNH" in txt_upper or "ĐỀ XUẤT PHẦN MỀM" in txt_upper or "SOFTWARE PROPOSAL" in txt_upper:
        return DocumentFamily.SOFTWARE_PROPOSAL, DocumentSubtype.SOFTWARE_PROPOSAL

    if "BIỂU MẪU" in txt_upper or "NỘI BỘ" in txt_upper:
        return DocumentFamily.INTERNAL_FORM, DocumentSubtype.INTERNAL_FORM

    return DocumentFamily.UNKNOWN, DocumentSubtype.UNKNOWN
