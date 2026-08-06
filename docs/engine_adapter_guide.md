# Engine Adapter Integration Guide

Hướng dẫn chi tiết cách thêm mới một Document Extraction Engine vào hệ thống Benchmark mà **không cần sửa đổi `BenchmarkController`**.

---

## 📋 Quyền hạn và Trách nhiệm của DocumentEngine Adapter

Theo nguyên tắc kiến trúc:
1. `DocumentEngine` chỉ chịu trách nhiệm đọc tài liệu và chuyển đổi thành `RawExtractionResult`.
2. **Không chứa**:
   - Business validation logic.
   - Excel export logic.
   - UI components.
   - Selection of final winner.

---

## 🛠 Bước 1: Tạo Adapter Class kế thừa `BaseDocumentEngine`

Tạo file mới tại `src/document_benchmark/engines/my_new_engine.py`:

```python
from typing import Optional, Dict, Any
from document_benchmark.engines.base import BaseDocumentEngine
from document_benchmark.core.contracts import EngineSpec, EngineHealth, DocumentInput, RawExtractionResult
from document_benchmark.core.statuses import EngineStatus

class MyNewEngine(BaseDocumentEngine):
    def __init__(self, spec: EngineSpec) -> None:
        super().__init__(spec)
        # Khởi tạo tham số cấu hình từ spec.options
        self.option_param = spec.options.get("param_key", "default_val")

    def healthcheck(self) -> EngineHealth:
        """Kiểm tra nhẹ nhàng sự tồn tại của thư viện/mô hình mà không nạp model nặng."""
        try:
            import my_lib
            return EngineHealth(
                engine_id=self.spec.engine_id,
                config_id=self.spec.config_id,
                status=EngineStatus.SUCCESS,
                available=True,
            )
        except ImportError:
            return EngineHealth(
                engine_id=self.spec.engine_id,
                config_id=self.spec.config_id,
                status=EngineStatus.UNAVAILABLE,
                available=False,
                error_message="my_lib package is not installed",
                missing_dependencies=["my_lib"],
            )

    def prepare(self) -> None:
        """Load weights/models vào bộ nhớ."""
        import my_lib
        self.model = my_lib.load_model()
        self._is_prepared = True

    def extract(self, document: DocumentInput, target_schema: Optional[Dict[str, Any]] = None) -> RawExtractionResult:
        """Thực hiện bóc tách tài liệu PDF và trả về RawExtractionResult."""
        # Gọi mô hình trích xuất
        extracted_text = self.model.predict(document.path)
        
        return RawExtractionResult(
            run_id="",
            document_id=document.document_id,
            engine_id=self.spec.engine_id,
            config_id=self.spec.config_id,
            output_kind=self.spec.output_kind,
            success=True,
            full_text=extracted_text,
            pages=[],
            tables=[],
            field_candidates={},
        )

    def close(self) -> None:
        """Giải phóng tài nguyên và file tạm."""
        self.model = None
        self._is_prepared = False
```

---

## ⚙️ Bước 2: Đăng ký Engine vào `EngineRegistry`

Mở [`src/document_benchmark/core/engine_registry.py`](file:///d:/Documents-engine/src/document_benchmark/core/engine_registry.py) và thêm mapping tự động vào `_try_lazy_register`:

```python
module_map = {
    "docling": ("document_benchmark.engines.docling_engine", "DoclingEngine"),
    "ppstructure_v3": ("document_benchmark.engines.ppstructure_engine", "PPStructureEngine"),
    "my_new_engine": ("document_benchmark.engines.my_new_engine", "MyNewEngine"),
}
```

---

## 📄 Bước 3: Tạo YAML Profile Cấu hình

Tạo file profile tại `configs/engines/my_new_engine.yaml`:

```yaml
engine_id: my_new_engine
engine_version: 1.0.0
config_id: my_new_engine_default_cpu
output_kind: document_ir
supports_pdf_text: true
supports_scanned_pdf: true
supports_tables: true
supports_gpu: false
supports_multi_page: true
provides_bounding_boxes: false
license_name: MIT
enabled: true
device: cpu
options:
  param_key: value
  timeout_seconds: 120
```

---

## 🧪 Bước 4: Viết Contract Test

Tạo test tại `tests/contract/test_my_new_engine_contract.py` để kiểm thử 4 hàm bắt buộc (`healthcheck`, `prepare`, `extract`, `close`).
