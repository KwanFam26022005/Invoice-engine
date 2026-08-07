"""Rule-based anchor classifier for business document families."""

import re
import unicodedata
from typing import Any, Dict, List, Tuple
from pydantic import BaseModel, Field

from document_engine.core.models import DocumentFamilyType
from document_engine.ir.models import DocumentIR


class ClassificationResult(BaseModel):
    document_family: DocumentFamilyType
    confidence: float
    matched_signals: List[str] = Field(default_factory=list)
    alternative_families: List[DocumentFamilyType] = Field(default_factory=list)
    requires_review: bool = False


class DocumentClassifier:
    def __init__(self):
        # Anchor keyword rules per document family
        self.rules: Dict[DocumentFamilyType, Dict[str, Any]] = {
            DocumentFamilyType.TAX_WITHHOLDING_CERTIFICATE: {
                "strong_anchors": [
                    "chúng từ khấu trừ thuế thu nhập cá nhân",
                    "chứng từ khấu trừ thuế thu nhập cá nhân",
                    "chung tu khau tru thue thu nhap ca nhan",
                    "certificate of personal income tax withholding",
                    "số thuế thu nhập cá nhân đã khấu trừ",
                    "so thue thu nhap ca nhan da khau tru",
                ],
                "weak_anchors": ["khấu trừ thuế", "khau tru thue", "thu nhập cá nhân", "pit withholding"],
                "min_score": 2,
            },
            DocumentFamilyType.PORT_SERVICE_INVOICE: {
                "strong_anchors": [
                    "container",
                    "teu",
                    "nâng hạ",
                    "nang ha",
                    "lưu bãi",
                    "luu bai",
                    "gate in",
                    "gate out",
                    "dịch vụ cảng",
                    "dich vu cang",
                ],
                "weak_anchors": ["cont", "bãi", "tàu", "cảng"],
                "min_score": 2,
            },
            DocumentFamilyType.UTILITY_CONSUMPTION_INVOICE: {
                "strong_anchors": [
                    "chỉ số cũ",
                    "chi so cu",
                    "chỉ số mới",
                    "chi so moi",
                    "sản lượng tiêu thụ",
                    "san luong tieu thu",
                    "kỳ hóa đơn",
                    "ky hoa don",
                ],
                "weak_anchors": ["kwh", "m3", "tiêu thụ", "điện lực", "cấp nước"],
                "min_score": 2,
            },
            DocumentFamilyType.SERVICE_VOLUME_INVOICE: {
                "strong_anchors": [
                    "khối lượng thực hiện",
                    "khoi luong thuc hien",
                    "số lượt",
                    "so luot",
                    "bảng tổng hợp dịch vụ",
                ],
                "weak_anchors": ["sản lượng", "đơn vị tính", "nghiệp vụ"],
                "min_score": 2,
            },
            DocumentFamilyType.SALES_INVOICE: {
                "strong_anchors": [
                    "hóa đơn giá trị gia tăng",
                    "hoa don gia tri gia tang",
                    "hóa đơn bán hàng",
                    "hoa don ban hang",
                    "vat invoice",
                    "sales invoice",
                ],
                "weak_anchors": ["hóa đơn", "hoa don", "invoice", "mẫu số", "ký hiệu"],
                "min_score": 2,
            },
            DocumentFamilyType.RECEIPT: {
                "strong_anchors": [
                    "phiếu thu",
                    "phieu thu",
                    "biên lai",
                    "bien lai",
                    "payment receipt",
                ],
                "weak_anchors": ["receipt", "đã nhận đủ số tiền"],
                "min_score": 2,
            },
            DocumentFamilyType.SUPPORTING_STATEMENT: {
                "strong_anchors": [
                    "bảng kê",
                    "bang ke",
                    "phụ lục hóa đơn",
                    "phu luc hoa don",
                    "supporting statement",
                ],
                "weak_anchors": ["phụ lục", "statement"],
                "min_score": 2,
            },
        }

    def _normalize_text(self, text: str) -> str:
        norm = unicodedata.normalize("NFC", text).lower()
        return re.sub(r"\s+", " ", norm)

    def classify(self, document_ir: DocumentIR) -> ClassificationResult:
        full_text = self._normalize_text(document_ir.full_text)
        if not full_text:
            return ClassificationResult(
                document_family=DocumentFamilyType.UNKNOWN,
                confidence=0.0,
                matched_signals=["empty_text"],
                requires_review=True,
            )

        scores: List[Tuple[DocumentFamilyType, int, List[str]]] = []

        for family, rule in self.rules.items():
            matched: List[str] = []
            score = 0

            for anchor in rule["strong_anchors"]:
                norm_anchor = self._normalize_text(anchor)
                if norm_anchor in full_text:
                    matched.append(f"strong:{anchor}")
                    score += 2

            for anchor in rule["weak_anchors"]:
                norm_anchor = self._normalize_text(anchor)
                if norm_anchor in full_text:
                    matched.append(f"weak:{anchor}")
                    score += 1

            if score >= rule["min_score"]:
                scores.append((family, score, matched))

        if not scores:
            return ClassificationResult(
                document_family=DocumentFamilyType.UNKNOWN,
                confidence=0.2,
                matched_signals=["no_strong_anchors_matched"],
                requires_review=True,
            )

        scores.sort(key=lambda x: x[1], reverse=True)
        top_family, top_score, top_matched = scores[0]

        confidence = min(1.0, round(top_score / 6.0, 2))
        requires_review = confidence < 0.3 or top_family == DocumentFamilyType.UNKNOWN

        alt_families = [item[0] for item in scores[1:]]

        return ClassificationResult(
            document_family=top_family,
            confidence=confidence,
            matched_signals=top_matched,
            alternative_families=alt_families,
            requires_review=requires_review,
        )
