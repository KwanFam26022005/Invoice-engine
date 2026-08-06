# Invoice Engine Benchmark

Hệ thống Local Benchmark đánh giá chất lượng và hiệu năng của các Document Extraction Engine trên các loại hóa đơn và biểu mẫu PDF tại Việt Nam.

---

## 🎯 Mục Tiêu Dự Án

Đánh giá, so sánh và lựa chọn Document Extraction Engine tối ưu (về độ chính xác bóc tách trường thông tin, thời gian xử lý và mức tiêu thụ tài nguyên CPU/RAM/GPU) trên tài liệu PDF hỗn hợp (Hóa đơn GTGT, Hóa đơn Điện & Nước, Hóa đơn bán hàng, Biển lai).

---

## 🧩 Engine Candidates

- **Docling** (Text-only CPU & Table recognition profiles)
- **PP-StructureV3** (PaddleOCR Vietnamese Table & Document IR)
- **PaddleOCR-VL** (Visual-Language OCR engine)
- **Sparrow Parse** (Layout & VLM parsing engine)

---

## 🏗 Kiến Trúc Hệ Thống

```text
PDF Input
  │
  ▼
DocumentEngine (Isolated Subprocess Runner)
  │
  ▼
Raw Extraction Result (Document IR / Bounding Boxes / Tables)
  │
  ▼
Canonical Normalization (High-Precision Decimal, Standard Dates, Tax IDs)
  │
  ▼
Business Validation Rules (subtotal - discount + VAT ≈ total_amount)
  │
  ▼
Evaluation (Cross-Engine Disagreement & Ground-Truth Matching)
  │
  ▼
DuckDB Aggregation (In-Memory SQL Financial Aggregates)
  │
  ▼
Excel / CSV Benchmark Reports & Business Output Workbooks
```

---

## ⚙️ Cài Đặt Môi Trường Base

```bash
# Clone repository
git clone https://github.com/KwanFam26022005/Invoice-engine.git
cd Invoice-engine

# Cài đặt package ở chế độ editable
python -m pip install -e .

# Cài đặt các thư viện bổ trợ cho testing và UI
python -m pip install pytest ruff streamlit duckdb openpyxl pypdf PyMuPDF
```

---

## 🧪 Chạy Test Suite

```bash
# Chạy 32 unit & contract tests
python -m pytest -v

# Kiểm tra Linter & Style Rules
python -m ruff check src tests scripts
```

---

## 📦 Chuẩn Bị và Kiểm Tra Dataset

### 1. Chạy Dataset Preparation Pipeline

```bash
python scripts/prepare_benchmark_dataset.py --dataset-root "D:\Documents-engine\datasets"
```

### 2. Kiểm Tra Integrity (Verify-Only Mode)

```bash
python scripts/prepare_benchmark_dataset.py --dataset-root "D:\Documents-engine\datasets" --verify-only
```

---

## 🔒 Chính Sách Không Commit Raw Documents

Toàn bộ file PDF hóa đơn gốc, file ảnh (JPG/PNG) và file nén ZIP **không được version-control trên Git** để tuân thủ quy định bảo mật thông tin.
Git chỉ lưu vết mã nguồn Python, cấu hình YAML, file manifests đã sanitize và phân chia benchmark splits (`smoke_test.txt`, `benchmark_full.txt`, `hard_cases.txt`).

---

## 📌 Trạng Thái Hiện Tại của Dự Án

- ✅ **Dataset Preparation**: Hoàn thành chuẩn bị corpus 51 image-only PDFs hợp lệ.
- ✅ **Test Coverage**: Passed 32/32 unit, contract, và integration tests.
- 🚀 **Bước tiếp theo**: Đánh giá benchmark quy mô lớn trên toàn bộ candidate engines.
