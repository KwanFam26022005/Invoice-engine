# Báo Cáo Kết Quả Chuẩn Bị Dataset Benchmark Document Extraction Engine

## 1. Cấu trúc dữ liệu

Local dataset root:

```text
D:\Documents-engine\datasets
```

Cấu trúc logic:

```text
datasets/
├── archives/
├── staging/
├── raw/
├── reference_merged/
├── benchmark/
│   ├── documents/
│   ├── ground_truth/
│   ├── manifests/
│   └── splits/
└── preparation_logs/
```

*Lưu ý*: Các thư mục chứa PDF, ZIP và dữ liệu raw không được commit vào repository public. Git chỉ quản lý script, manifest đã sanitize, split và báo cáo.

---

## 2. Thống kê

| Chỉ số | Số lượng |
|---|---:|
| Archive ZIP | 3 |
| Tổng PDF phát hiện | 54 |
| PDF đơn lẻ | 51 |
| PDF merged | 3 |
| PDF benchmark hợp lệ | 51 |
| Duplicate | 0 |
| Non-PDF/invalid entries | 2 |
| Image-only PDF | 51 |
| Text-layer PDF | 0 |

### Phân phối Category

| Category | Số lượng |
|---|---:|
| vat_discount | 3 |
| utilities | 10 |
| sales_receipts | 38 |

---

## 3. Benchmark splits

### `smoke_test.txt` (10 document IDs)

- `VATD-0001`
- `VATD-0002`
- `UTIL-0001`
- `UTIL-0002`
- `UTIL-0003`
- `SALE-0001`
- `SALE-0002`
- `SALE-0003`
- `SALE-0004`
- `SALE-0005`

### `benchmark_full.txt`

- 51 document IDs hợp lệ.

### `hard_cases.txt`

- 51 document IDs.
- Tất cả hiện là image-only/scanned PDF.

---

## 4. Verification

### Dataset preparation

```bash
python scripts/prepare_benchmark_dataset.py --dataset-root "D:\Documents-engine\datasets"
```

### Ruff Linter

```bash
python -m ruff check src tests scripts
```

*Kết quả*: All checks passed.

### Pytest Test Suite

```bash
python -m pytest -v
```

*Kết quả*: 32 tests passed.

---

## 5. Kết luận

Corpus hiện tại thích hợp cho benchmark OCR và document parsing trên image-only PDF. Corpus chưa đánh giá được fast path dành cho native text-layer PDF; cần bổ sung text-layer PDF trong giai đoạn sau.
