# Hướng dẫn sử dụng Single-Document Engine Comparison UI

Tài liệu hướng dẫn vận hành và khai thác giao diện so sánh trực quan từng tài liệu (**Single-Document Engine Comparison UI**) trong dự án Document Extraction Engine Benchmark.

---

## 1. Mục tiêu ứng dụng

Ứng dụng phục vụ so sánh trực quan, đọc trực tiếp dữ liệu có sẵn từ kết quả thực thi benchmark (campaign) giữa hai cấu hình:
1. `docling_ocr_easyocr_vi_cpu` (Docling OCR — EasyOCR VI/EN)
2. `ppstructure_v3_vi_table_cpu` (PP-StructureV3 — VI Table CPU)

trên 10 tài liệu thuộc smoke benchmark (`runs/smoke/smoke_scan_baseline_001`).

---

## 2. Cách chạy ứng dụng

### Cách 1: Chạy qua Launcher Script (Khuyên dùng)

```bash
python scripts/run_comparison_ui.py `
  --campaign-dir "D:\Documents-engine\runs\smoke\smoke_scan_baseline_001" `
  --dataset-root "D:\Documents-engine\datasets"
```

### Cách 2: Chạy trực tiếp qua Streamlit CLI

```bash
python -m streamlit run src/document_benchmark/ui/comparison_app.py -- `
  --campaign-dir "D:\Documents-engine\runs\smoke\smoke_scan_baseline_001" `
  --dataset-root "D:\Documents-engine\datasets"
```

---

## 3. Ranh giới an toàn & Bảo mật (Security & Boundaries)

- **Local-first & Read-only**: UI tuyệt đối không gọi model, không nạp weights và không thực thi OCR inference.
- **Ranh giới No-Ground-Truth**: Campaign hiện tại có `ground_truth_level = 0` và `accuracy_status = NOT_COMPUTED_NO_GROUND_TRUTH`. Mọi tab hiển thị cố định banner:
  > *"Không có ground truth. Các chỉ số bên dưới không đại diện cho accuracy."*
- **Path Containment Check**: Mọi truy xuất file PDF đều được kiểm tra nghiêm ngặt xem có nằm trong `dataset_root` hay không. Mọi kết quả raw JSON/logs đều phải nằm trong `campaign_dir` để ngăn chặn Path Traversal.
- **No Unsafe HTML**: Không thực thi script từ HTML table hay unescaped OCR text.

---

## 4. Cấu trúc 7 Tab chính

1. **📊 1. Tổng quan**: Xem trước trang PDF gốc (Base64 / PyMuPDF PNG), thẻ tóm tắt hai engine, biểu đồ so sánh latency measured repeats, Tỷ lệ tốc độ (Speed Ratio = `Docling mean / PP mean`).
2. **🔤 2. Văn bản OCR**: 3 chế độ xem văn bản trích xuất (Raw Side-by-Side, Normalized Side-by-Side, Unified Diff), chỉ số tương đồng mô tả (`difflib` SequenceMatcher labeled *"Độ tương đồng mô tả"*), công cụ tìm kiếm và lọc diacritic.
3. **📋 3. Trường dữ liệu**: Bảng hợp nhất (Union) các field candidates, nhãn trạng thái (`Đồng thuận hoàn toàn`, `Đồng thuận sau chuẩn hóa`, `Khác biệt`, `Chỉ có ở Docling`, `Chỉ có ở PP-StructureV3`, `Cần kiểm tra thủ công`).
4. **📐 4. Bảng**: So sánh cấu trúc bảng trích xuất, subtabs (Visual table, Raw payload, Structure metadata), chỉ số `Structural similarity`.
5. **📍 5. Bố cục**: Tọa độ geometry bounding boxes overlay (layout boxes & OCR text boxes) từ PP-StructureV3.
6. **⚡ 6. Hiệu năng**: Bảng measured repeats, biểu đồ latency/RAM/CPU, tách biệt Cold Prepare time và Warm Extraction latency.
7. **🔍 7. Chẩn đoán**: Kiểm tra provenance mismatch (phiên bản package giữa `environment.json` và `runtime_metadata`), xem tail 200 dòng logs, xem Raw JSON.

---

## 5. Download & Export dữ liệu

Giao diện cho phép tải xuống các file liên quan đến tài liệu đang chọn:
- `Docling Full Text (.txt)` & `PP-StructureV3 Full Text (.txt)`
- `Field Comparison (.csv)`
- `Selected Document Summary (.json)`

---

## 6. Known Limitations (Hạn chế đã biết)

1. **CPU Metric Caveat**: CPU peak percent có thể trả về `0.0` nếu thư viện psutil không ghi nhận mẫu trong khoảng thời gian extraction ngắn. UI hiển thị badge cảnh báo `CPU metric có thể không hợp lệ`.
2. **Batch-level Resource Sampling**: Tài nguyên RAM/CPU hiện được tổng hợp ở cấp worker process batch.
3. **Geometry Overlay**: Bounding box hiện chủ yếu khả thi với PP-StructureV3 payload (`layout_det_res`, `overall_ocr_res`).
