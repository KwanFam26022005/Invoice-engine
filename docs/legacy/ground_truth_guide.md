# Ground Truth Specification & Guide

Tài liệu định nghĩa 3 cấp độ Ground Truth hỗ trợ trong hệ thống Benchmark.

---

## 📌 Ground Truth Levels

### Level 0: Unsupervised / No Ground Truth
- Không cần file JSON ground truth.
- Đánh giá dựa trên:
  1. Business validation integrity (`subtotal - discount + VAT ≈ total_amount`).
  2. Cross-engine disagreement severity (Consensus table).
  3. Required-field completeness.
  4. Success, Timeout, Crash rate.

---

### Level 1: Critical Fields Ground Truth
So sánh trực tiếp các trường thông tin quan trọng.

Ví dụ file `datasets/ground_truth/sample_invoice_gt.json`:

```json
{
  "document_id": "doc_sample_invoice",
  "document_family": "invoice",
  "canonical_payload": {
    "invoice_number": "0001234",
    "invoice_series": "1K24TAA",
    "invoice_date": "2024-05-10",
    "seller_tax_id": "0101234567",
    "seller_name": "CÔNG TY TNHH LOGISTICS TOÀN CẦU",
    "buyer_tax_id": "0309876543",
    "buyer_name": "CÔNG TY CP VẬN TẢI BIỂN VIỆT NAM",
    "subtotal": "10000000.00",
    "vat_amount": "1000000.00",
    "total_amount": "11000000.00"
  }
}
```

---

### Level 2: Full Line-Item Ground Truth
So sánh chi tiết từng dòng mặt hàng / sản phẩm.

```json
{
  "document_id": "doc_sample_invoice",
  "document_family": "invoice",
  "canonical_payload": {
    "invoice_number": "0001234",
    "total_amount": "11000000.00",
    "line_items": [
      {
        "line_number": 1,
        "description": "Dịch vụ vận chuyển container",
        "unit": "Chuyến",
        "quantity": "2",
        "unit_price": "5000000.00",
        "amount_after_tax": "10000000.00"
      }
    ]
  }
}
```
