"""Utility Consumption Invoice specialized family mapper."""

from decimal import Decimal
from typing import Dict, List, Tuple

from document_engine.extraction.evidence import find_text_evidence
from document_engine.extraction.normalizer import parse_decimal
from document_engine.ir.models import DocumentIR
from document_engine.schemas.family_schemas import (
    CommonDocumentFields,
    FieldCandidate,
    MeterReading,
    PricingTier,
    UtilityConsumptionInvoicePayload,
)


class UtilityConsumptionMapper:
    def map(
        self, document_ir: DocumentIR
    ) -> Tuple[UtilityConsumptionInvoicePayload, Dict[str, FieldCandidate]]:
        field_candidates: Dict[str, FieldCandidate] = {}

        # 1. Billing Period
        period_raw, period_ev = find_text_evidence(
            document_ir, r"(?:kỳ thanh toán|ky thanh toan|billing period)\s*:\s*([^\n]+)"
        )
        if period_raw:
            field_candidates["billing_period"] = FieldCandidate(
                value=period_raw, raw_value=period_raw, evidence_references=period_ev
            )

        # 2. Customer / Contract Number
        contract_num, _contract_ev = find_text_evidence(
            document_ir, r"(?:mã khách hàng|ma khach hang|số hợp đồng|contract no)\s*:\s*([A-Za-z0-9\-]+)"
        )

        # 3. Service Location
        location, _location_ev = find_text_evidence(
            document_ir, r"(?:địa chỉ sử dụng|dia chi su dung|location)\s*:\s*([^\n]+)"
        )

        # 4. Meter Readings
        meter_num, _meter_ev = find_text_evidence(
            document_ir, r"(?:số công tơ|so cong to|meter no)\s*:\s*([A-Za-z0-9\-]+)"
        )
        op_raw, _op_ev = find_text_evidence(
            document_ir, r"(?:chỉ số đầu|chi so dau|opening reading)\s*:\s*([\d\.,]+)"
        )
        cl_raw, _cl_ev = find_text_evidence(
            document_ir, r"(?:chỉ số cuối|chi so cuoi|closing reading)\s*:\s*([\d\.,]+)"
        )
        cons_raw, _cons_ev = find_text_evidence(
            document_ir, r"(?:sản lượng|san luong|tiêu thụ|consumption)\s*:\s*([\d\.,]+)"
        )

        op_dec = parse_decimal(op_raw)[0] if op_raw else None
        cl_dec = parse_decimal(cl_raw)[0] if cl_raw else None
        cons_dec = parse_decimal(cons_raw)[0] if cons_raw else None

        # Unit detection: kWh or m3
        full_text_lower = document_ir.full_text.lower()
        unit_str = "m³" if "m3" in full_text_lower or "m³" in full_text_lower else "kWh"
        meas_type = "water" if unit_str == "m³" else "electricity"

        meter_readings: List[MeterReading] = []
        if any([meter_num, op_dec, cl_dec, cons_dec]):
            meter_readings.append(
                MeterReading(
                    meter_number=meter_num,
                    measurement_type=meas_type,
                    unit=unit_str,
                    opening_reading=op_dec,
                    closing_reading=cl_dec,
                    conversion_factor=Decimal("1.0"),
                    consumption=cons_dec or (cl_dec - op_dec if cl_dec and op_dec else None),
                )
            )

        # 5. Pricing Tiers from TableIR
        pricing_tiers: List[PricingTier] = []
        for page in document_ir.pages:
            for table in page.tables:
                if table.row_count > 1:
                    rows_dict: Dict[int, Dict[int, str]] = {}
                    for c in table.cells:
                        rows_dict.setdefault(c.row_index, {})[c.col_index] = c.text

                    for r_idx in sorted(rows_dict.keys()):
                        if r_idx == 0:
                            continue
                        r_data = rows_dict[r_idx]
                        texts = [r_data.get(col, "") for col in sorted(r_data.keys())]
                        if not any(texts):
                            continue

                        name = texts[0] if len(texts) > 0 else f"Tier {r_idx}"
                        qty = parse_decimal(texts[1])[0] if len(texts) > 1 else None
                        price = parse_decimal(texts[2])[0] if len(texts) > 2 else None
                        amt = parse_decimal(texts[3])[0] if len(texts) > 3 else None

                        pricing_tiers.append(
                            PricingTier(
                                tier_name=name,
                                quantity=qty,
                                unit=unit_str,
                                unit_price=price,
                                amount=amt,
                            )
                        )

        # 6. Grand Total
        grand_raw, grand_ev = find_text_evidence(
            document_ir, r"(?:tổng cộng|tong cong|total)\s*:\s*([\d\.,\s]+)"
        )
        grand_total = parse_decimal(grand_raw)[0] if grand_raw else None
        if grand_total is not None:
            field_candidates["grand_total"] = FieldCandidate(
                value=str(grand_total), raw_value=grand_raw, evidence_references=grand_ev
            )

        common = CommonDocumentFields(
            billing_period=period_raw,
            currency="VND",
            grand_total=grand_total,
        )

        payload = UtilityConsumptionInvoicePayload(
            common=common,
            service_location=location,
            contract_number=contract_num,
            meter_readings=meter_readings,
            pricing_tiers=pricing_tiers,
        )
        return payload, field_candidates
