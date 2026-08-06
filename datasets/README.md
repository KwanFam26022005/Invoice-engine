# Document Benchmark Dataset Management

Tài liệu hướng dẫn quản lý, chuẩn bị và nghiệm thu dữ liệu Benchmark cho Document Extraction Engine.

---

## 🔒 Quy định Bảo mật và Version Control (Git Policy)

1. **Không commit file nhị phân tài liệu**: Toàn bộ file PDF hóa đơn, hình ảnh (JPG, PNG, TIFF) và file nén (ZIP) **không được lưu trên Git repository public** để bảo vệ tính riêng tư và bảo mật thông tin doanh nghiệp.
2. **Các thành phần được quản lý qua Git**:
   - Thư viện mã nguồn Python (`src/`, `scripts/`, `tests/`).
   - Các file cấu hình benchmark và validation schema (`configs/`).
   - Các file Metadata và Manifests đã được làm sạch (`datasets/benchmark/manifests/documents.csv`, `documents.jsonl`, `duplicates.csv`).
   - Các file phân chia Benchmark Splits (`datasets/benchmark/splits/smoke_test.txt`, `benchmark_full.txt`, `hard_cases.txt`).
   - Log tổng hợp và danh sách file không hợp lệ (`datasets/preparation_logs/summary.json`, `invalid_files.csv`).

---

## 📁 Cấu Trúc Dữ Liệu Local (`D:\Documents-engine\datasets`)

Sau khi giải nén và xử lý, cấu trúc dữ liệu local bao gồm:

```text
datasets/
├── archives/               # Lưu trữ 3 file ZIP gốc
├── staging/                # Giải nén tạm thời theo category
├── raw/                    # Tài liệu PDF hóa đơn gốc (Bất biến)
├── reference_merged/       # Các file PDF gộp (Merged multi-page reference)
├── benchmark/
│   ├── documents/          # Các file PDF đơn lẻ đã chuẩn hóa tên
│   │   ├── vat_discount/   (VATD-0001 ... VATD-0003)
│   │   ├── utilities/      (UTIL-0001 ... UTIL-0010)
│   │   └── sales_receipts/ (SALE-0001 ... SALE-0038)
│   ├── ground_truth/       # Ground truth JSON (Level 1 / Level 2)
│   ├── manifests/          # Manifests CSV và JSONL (Lưu trên Git)
│   └── splits/             # Danh sách document_id theo split (Lưu trên Git)
└── preparation_logs/       # Log chuẩn bị và summary.json (Lưu trên Git)
```

---

## 🛠 Hướng Dẫn Tái Tạo Dữ Liệu Local

### 1. Đặt các Archive ZIP vào `datasets/`

Đặt 3 file ZIP nguồn vào thư mục `datasets/`:
- `mau_hd_gtgt_thue_tong_co_chiet_khau_pdf.zip`
- `mau_hd_gtgt_dien_va_nuoc_pdf.zip`
- `mau_hd_ban_hang_va_bien_lai_pdf.zip`

### 2. Chạy Pipeline Chuẩn Bị Dữ Liệu

```bash
python scripts/prepare_benchmark_dataset.py --dataset-root "D:\Documents-engine\datasets"
```

### 3. Kiểm Tra Integrity (Verify-Only Mode)

```bash
python scripts/prepare_benchmark_dataset.py --dataset-root "D:\Documents-engine\datasets" --verify-only
```

---

## 📊 Thống Kê Dataset Corpus Hiện Tại

- **Tổng số ZIP Archive**: 3
- **Tổng số PDF phát hiện**: 54 (51 PDF đơn lẻ + 3 PDF merged reference)
- **Số PDF Benchmark hợp lệ**: 51
- **Số file Duplicate (SHA-256)**: 0
- **Số file Non-PDF (manifest.txt)**: 2
- **Số Image-only PDF**: 51 (100% hóa đơn scanned)
- **Số Text-layer PDF**: 0

### Phân phối Category:
- `vat_discount`: 3 PDFs
- `utilities`: 10 PDFs
- `sales_receipts`: 38 PDFs

### Phân phối Benchmark Splits:
- `smoke_test.txt`: 10 document IDs (2 vat_discount, 3 utilities, 5 sales_receipts)
- `benchmark_full.txt`: 51 document IDs
- `hard_cases.txt`: 51 document IDs (toàn bộ image-only/scanned PDFs)
