"""Unit tests for document family classifier."""

from document_engine.classification.classifier import DocumentClassifier
from document_engine.core.models import DocumentFamilyType, PDFProfileType
from document_engine.ir.models import (
    DocumentIR,
    DocumentProfile,
    ParserProvenance,
    SourceDocument,
)


def create_mock_doc_ir(text: str) -> DocumentIR:
    return DocumentIR(
        document_id="doc_mock123",
        source_document=SourceDocument(
            document_id="doc_mock123",
            filename="mock.pdf",
            path="/tmp/mock.pdf",
            sha256="mockhash123",
            page_count=1,
        ),
        profile=DocumentProfile(
            pdf_profile=PDFProfileType.NATIVE_PDF,
            has_text_layer=True,
        ),
        provenance=ParserProvenance(
            parser_id="pymupdf_native",
            parser_version="1.0.0",
        ),
        full_text=text,
    )


def test_classify_sales_invoice():
    text = "HÓA ĐƠN GIÁ TRỊ GIA TĂNG\nMẫu số: 01GTKT0/001\nKý hiệu: AA/26E\nSố: 0001234"
    doc_ir = create_mock_doc_ir(text)
    classifier = DocumentClassifier()
    res = classifier.classify(doc_ir)

    assert res.document_family == DocumentFamilyType.SALES_INVOICE
    assert res.confidence > 0.3
    assert res.requires_review is False


def test_classify_tax_withholding_certificate():
    text = "CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM\nCHỨNG TỪ KHẤU TRỪ THUẾ THU NHẬP CÁ NHÂN\nSố thuế thu nhập cá nhân đã khấu trừ: 500.000 VNĐ"
    doc_ir = create_mock_doc_ir(text)
    classifier = DocumentClassifier()
    res = classifier.classify(doc_ir)

    assert res.document_family == DocumentFamilyType.TAX_WITHHOLDING_CERTIFICATE
    assert res.confidence >= 0.5


def test_classify_port_service_invoice():
    text = "HÓA ĐƠN DỊCH VỤ CẢNG\nSố container: TCNU1234567\nPhí nâng hạ 20 feet TEU lưu bãi gate in"
    doc_ir = create_mock_doc_ir(text)
    classifier = DocumentClassifier()
    res = classifier.classify(doc_ir)

    assert res.document_family == DocumentFamilyType.PORT_SERVICE_INVOICE


def test_classify_unknown_document():
    text = "Tài liệu ngẫu nhiên không có từ khóa nghiệp vụ nào"
    doc_ir = create_mock_doc_ir(text)
    classifier = DocumentClassifier()
    res = classifier.classify(doc_ir)

    assert res.document_family == DocumentFamilyType.UNKNOWN
    assert res.requires_review is True
