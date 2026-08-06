"""Mock engine implementation for testing pipeline skeleton without heavy dependencies."""

import time
from datetime import datetime, timezone
from typing import Any

from document_benchmark.core.contracts import (
    DocumentInput,
    EngineHealth,
    EngineSpec,
    RawExtractionResult,
)
from document_benchmark.core.statuses import EngineStatus
from document_benchmark.engines.base import BaseDocumentEngine


class MockEngine(BaseDocumentEngine):
    """Mock document extraction engine for testing benchmark execution pipeline."""

    def __init__(self, spec: EngineSpec) -> None:
        super().__init__(spec)
        opts = spec.options or {}
        self.prepare_delay_ms: float = float(opts.get("prepare_delay_ms", 10))
        self.extract_delay_ms: float = float(opts.get("extract_delay_ms", 50))
        self.should_fail: bool = bool(opts.get("should_fail", False))
        self.failure_reason: str = str(opts.get("failure_reason", "Simulated MockEngine failure"))
        self.mock_family: str = str(opts.get("mock_family", "invoice"))

    def healthcheck(self) -> EngineHealth:
        if self.spec.options.get("healthcheck_fail", False):
            return EngineHealth(
                engine_id=self.spec.engine_id,
                config_id=self.spec.config_id,
                status=EngineStatus.UNAVAILABLE,
                available=False,
                error_message="MockEngine healthcheck failure simulated",
                missing_dependencies=["simulated_missing_dep"],
            )
        return EngineHealth(
            engine_id=self.spec.engine_id,
            config_id=self.spec.config_id,
            status=EngineStatus.SUCCESS,
            available=True,
        )

    def prepare(self) -> None:
        if self.prepare_delay_ms > 0:
            time.sleep(self.prepare_delay_ms / 1000.0)
        self._is_prepared = True

    def extract(
        self,
        document: DocumentInput,
        target_schema: dict[str, Any] | None = None,
    ) -> RawExtractionResult:
        started_at = datetime.now(timezone.utc)
        start_t = time.perf_counter()

        if self.extract_delay_ms > 0:
            time.sleep(self.extract_delay_ms / 1000.0)

        if self.should_fail:
            completed_at = datetime.now(timezone.utc)
            exec_time = (time.perf_counter() - start_t) * 1000.0
            return RawExtractionResult(
                run_id="",
                document_id=document.document_id,
                engine_id=self.spec.engine_id,
                config_id=self.spec.config_id,
                output_kind=self.spec.output_kind,
                success=False,
                error_type="MockExtractionFailure",
                error_message=self.failure_reason,
                started_at=started_at,
                completed_at=completed_at,
                execution_time_ms=exec_time,
            )

        # Generate realistic mock extraction data according to requested doc family
        raw_payload, full_text, pages, tables, field_candidates = self._generate_mock_payload(
            document
        )

        completed_at = datetime.now(timezone.utc)
        exec_time = (time.perf_counter() - start_t) * 1000.0

        return RawExtractionResult(
            run_id="",
            document_id=document.document_id,
            engine_id=self.spec.engine_id,
            config_id=self.spec.config_id,
            output_kind=self.spec.output_kind,
            success=True,
            raw_payload=raw_payload,
            full_text=full_text,
            pages=pages,
            tables=tables,
            field_candidates=field_candidates,
            warnings=[],
            started_at=started_at,
            completed_at=completed_at,
            execution_time_ms=exec_time,
        )

    def _generate_mock_payload(self, document: DocumentInput):
        pages = []
        for p in range(1, document.page_count + 1):
            pages.append(
                {
                    "page_number": p,
                    "text": f"Mock page {p} content for {document.filename}",
                    "width": 595.0,
                    "height": 842.0,
                }
            )

        if self.mock_family == "office_supply_request":
            full_text = "PHIẾU ĐỀ NGHỊ MUA VĂN PHÒNG PHẨM\nNgày: 15/05/2024\nNgười đề nghị: Nguyễn Văn A\nBộ phận: Hành chính"
            field_candidates = {
                "request_title": "Phiếu đề nghị mua văn phòng phẩm T5/2024",
                "request_date": "15/05/2024",
                "requester_name": "Nguyễn Văn A",
                "requester_department": "Phòng Hành chính - Nhân sự",
                "total_amount": "2.500.000",
            }
            tables = [
                {
                    "table_index": 0,
                    "page_number": 1,
                    "headers": ["STT", "Tên hàng", "ĐVT", "Số lượng", "Đơn giá", "Thành tiền"],
                    "rows": [
                        ["1", "Bút bi Thiên Long", "Hộp", "10", "50.000", "500.000"],
                        ["2", "Giấy A4 Double A 70gsm", "Ram", "20", "100.000", "2.000.000"],
                    ],
                }
            ]
        elif self.mock_family == "software_proposal":
            full_text = "TỜ TRÌNH ĐỀ XUẤT MUA PHẦN MỀM\nNgày: 20/05/2024\nTên phần mềm: Logistics Management System"
            field_candidates = {
                "proposal_title": "Tờ trình đăng ký bản quyền phần mềm quản lý kho",
                "proposal_date": "20/05/2024",
                "requester_name": "Trần Văn B",
                "requester_department": "Phòng IT",
                "software_name": "LogiCloud Enterprise",
                "supplier_name": "Công ty TNHH Giải Pháp Số",
                "number_of_users": "50",
                "estimated_cost": "120.000.000",
                "currency": "VND",
            }
            tables = []
        else:
            # Default invoice
            full_text = (
                "HÓA ĐƠN GIÁ TRỊ GIA TĂNG\nKý hiệu: 1K24TAA\nSố: 0001234\nNgày 10 tháng 05 năm 2024\n"
                "Tên đơn vị bán: CÔNG TY TNHH LOGISTICS TOÀN CẦU\nMã số thuế: 0101234567\n"
                "Tên đơn vị mua: CÔNG TY CP VẬN TẢI BIỂN VIỆT NAM\nMã số thuế: 0309876543\n"
                "Cộng tiền hàng: 10.000.000\nTiền thuế GTGT (10%): 1.000.000\nTổng cộng tiền thanh toán: 11.000.000 VND"
            )
            field_candidates = {
                "invoice_number": "0001234",
                "invoice_series": "1K24TAA",
                "invoice_date": "10/05/2024",
                "seller_name": "CÔNG TY TNHH LOGISTICS TOÀN CẦU",
                "seller_tax_id": "0101234567",
                "seller_address": "123 Đường Lê Duẩn, Q.1, TP.HCM",
                "buyer_name": "CÔNG TY CP VẬN TẢI BIỂN VIỆT NAM",
                "buyer_tax_id": "0309876543",
                "buyer_address": "456 Đường Nguyễn Huệ, Q.1, TP.HCM",
                "currency": "VND",
                "subtotal": "10.000.000",
                "discount_amount": "0",
                "vat_amount": "1.000.000",
                "total_amount": "11.000.000",
                "payment_method": "Chuyển khoản",
                "amount_in_words": "Mười một triệu đồng chẵn",
            }
            tables = [
                {
                    "table_index": 0,
                    "page_number": 1,
                    "headers": [
                        "STT",
                        "Tên hàng hóa, dịch vụ",
                        "ĐVT",
                        "Số lượng",
                        "Đơn giá",
                        "Thành tiền",
                    ],
                    "rows": [
                        ["1", "Dịch vụ vận chuyển container", "Chuyến", "2", "5.000.000", "10.000.000"]
                    ],
                }
            ]

        raw_payload = {
            "engine": self.spec.engine_id,
            "mock_family": self.mock_family,
            "full_text": full_text,
            "pages": pages,
            "tables": tables,
            "field_candidates": field_candidates,
        }

        return raw_payload, full_text, pages, tables, field_candidates

    def close(self) -> None:
        super().close()
