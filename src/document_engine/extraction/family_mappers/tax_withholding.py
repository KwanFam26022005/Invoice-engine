"""Tax Withholding Certificate specialized family mapper."""

from typing import Dict, Tuple

from document_engine.extraction.evidence import find_anchor_value
from document_engine.extraction.normalizer import normalize_tax_id, parse_date, parse_decimal
from document_engine.ir.models import DocumentIR, EvidenceReference
from document_engine.schemas.family_schemas import (
    CommonDocumentFields,
    FieldCandidate,
    Party,
    TaxWithholdingCertificatePayload,
)


class TaxWithholdingMapper:
    def map(
        self, document_ir: DocumentIR
    ) -> Tuple[TaxWithholdingCertificatePayload, Dict[str, FieldCandidate]]:
        field_candidates: Dict[str, FieldCandidate] = {}

        # 1. Form & Serial & Cert Number
        form_num, form_ev = find_anchor_value(document_ir, r"(?:mẫu số|mau so|form no)", r"[A-Za-z0-9/\-]+")
        serial_num, serial_ev = find_anchor_value(document_ir, r"(?:ký hiệu|ky hieu|serial no)", r"[A-Za-z0-9/\-]+")
        cert_num, cert_ev = find_anchor_value(
            document_ir,
            r"(?:số chứng từ|so chung tu|certificate no|số \(no\)|(?:^|\n)\s*(?:số|so)\s*:)",
            r"[A-Za-z0-9/\-]+",
        )
        for key, value, evidence in (("form_number", form_num, form_ev), ("serial_number", serial_num, serial_ev), ("certificate_number", cert_num, cert_ev)):
            if value:
                field_candidates[key] = FieldCandidate(value=value, raw_value=value, evidence_references=evidence)

        # 2. Payer Organization (Bên trả thu nhập)
        payer_name, payer_name_ev = find_anchor_value(document_ir, r"(?:\[01\].{0,80}tên tổ chức trả thu nhập|tên tổ chức trả thu nhập|to chuc tra thu nhap)")
        payer_tax, payer_tax_ev = find_anchor_value(document_ir, r"(?:\[02\].{0,80}mã số thuế|mã số thuế tổ chức trả|mst tổ chức|mst bên trả)", r"[\d\s\-]+")
        payer_party = Party(
            name=payer_name,
            tax_id=normalize_tax_id(payer_tax)[0] if payer_tax else None,
        )

        # 3. Recipient (Cá nhân khấu trừ)
        recip_name, recip_name_ev = find_anchor_value(document_ir, r"(?:\[05\].{0,80}(?:họ và tên|tên)|họ và tên|ho va ten|người nộp thuế|recipient)")
        recip_tax, recip_tax_ev = find_anchor_value(document_ir, r"(?:\[06\].{0,80}mã số thuế|mã số thuế cá nhân|mst cá nhân)", r"[\d\s\-]+")
        recip_party = Party(
            name=recip_name,
            tax_id=normalize_tax_id(recip_tax)[0] if recip_tax else None,
        )

        for key, value, evidence in (("income_paying_organization.name", payer_name, payer_name_ev), ("income_paying_organization.tax_id", payer_tax, payer_tax_ev), ("recipient.name", recip_name, recip_name_ev), ("recipient.tax_id", recip_tax, recip_tax_ev)):
            if value:
                field_candidates[key] = FieldCandidate(value=normalize_tax_id(value)[0] if key.endswith("tax_id") else value, raw_value=value, evidence_references=evidence)

        # 4. Incomes & Tax
        taxable_raw, _taxable_ev = find_anchor_value(
            document_ir,
            r"(?:tổng thu nhập chịu thuế|tong thu nhap chiu thue)",
            r"[\d\., ]+(?:\s*(?:đ|vnd))?",
        )
        taxable_dec = parse_decimal(taxable_raw)[0] if taxable_raw else None
        calculation_raw, calculation_ev = find_anchor_value(
            document_ir,
            r"(?:tổng thu nhập tính thuế|tong thu nhap tinh thue)",
            r"[\d\., ]+(?:\s*(?:đ|vnd))?",
        )
        calculation_dec = parse_decimal(calculation_raw)[0] if calculation_raw else None

        withheld_raw, withheld_ev = find_anchor_value(
            document_ir,
            r"(?:số thuế đã khấu trừ|so thue da khau tru|so thue thu nhap ca nhan da khau tru|withheld tax)",
            r"[\d\., ]+(?:\s*(?:đ|vnd))?",
        )
        withheld_dec = parse_decimal(withheld_raw)[0] if withheld_raw else None

        if withheld_dec is not None:
            field_candidates["withheld_tax"] = FieldCandidate(
                value=str(withheld_dec), raw_value=withheld_raw, evidence_references=withheld_ev
            )
        for key, value, raw, evidence in (("total_taxable_income", taxable_dec, taxable_raw, _taxable_ev), ("total_tax_calculation_income", calculation_dec, calculation_raw, calculation_ev)):
            if value is not None:
                field_candidates[key] = FieldCandidate(value=str(value), raw_value=raw, evidence_references=evidence)

        # 5. Dates
        sig_date_raw, sig_date_ev = find_anchor_value(document_ir, r"(?:ngày ký|ngay ky|signature date|ngày \(date\))", r"(?:\d{1,2}[\/\-\.]\d{1,2}[\/\-\.]\d{4}|(?:ngày\s*)?\d{1,2}\s*tháng\s*(?:\(month\)\s*)?\d{1,2}\s*năm\s*(?:\(year\)\s*)?\d{4})")
        sig_date = parse_date(sig_date_raw)[0] if sig_date_raw else None
        lookup_code, _lookup_ev = find_anchor_value(document_ir, r"(?:mã tra cứu|ma tra cuu|lookup code)", r"[A-Za-z0-9\-]+")
        payment_period, period_ev = _find_payment_period(document_ir)
        if payment_period:
            field_candidates["payment_period"] = FieldCandidate(value=payment_period, raw_value=payment_period, evidence_references=period_ev)
        if sig_date:
            field_candidates["signature_date"] = FieldCandidate(value=sig_date, raw_value=sig_date_raw, evidence_references=sig_date_ev)
        if lookup_code:
            field_candidates["lookup_code"] = FieldCandidate(value=lookup_code, raw_value=lookup_code, evidence_references=_lookup_ev)

        common = CommonDocumentFields(
            document_number=cert_num,
            document_series=serial_num,
            currency="VND",
            seller=payer_party,
            buyer=recip_party,
            grand_total=withheld_dec,
        )

        payload = TaxWithholdingCertificatePayload(
            common=common,
            form_number=form_num,
            serial_number=serial_num,
            certificate_number=cert_num,
            income_paying_organization=payer_party,
            recipient=recip_party,
            payment_period=payment_period,
            total_taxable_income=taxable_dec,
            total_tax_calculation_income=calculation_dec,
            withheld_tax=withheld_dec,
            signature_date=sig_date,
            lookup_code=lookup_code,
        )
        return payload, field_candidates


def _find_payment_period(
    document_ir: DocumentIR,
) -> Tuple[str | None, list[EvidenceReference]]:
    """Extract an indexed Vietnamese payment period without crossing pages."""
    start, start_ev = find_anchor_value(document_ir, r"từ tháng", r"\d{1,2}")
    end, end_ev = find_anchor_value(document_ir, r"đến tháng", r"\d{1,2}")
    year, year_ev = find_anchor_value(document_ir, r"năm", r"\d{4}")
    evidence = [*start_ev, *end_ev, *year_ev]
    if (
        start
        and end
        and year
        and len(evidence) == 3
        and len({item.page_number for item in evidence}) == 1
    ):
        return f"{year}-{int(start):02d}/{year}-{int(end):02d}", evidence
    return None, []
