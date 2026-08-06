"""Canonical normalizer mapping RawExtractionResult into normalized CanonicalExtractionResult."""

from decimal import Decimal
from typing import Any, Dict, List, Tuple

from document_benchmark.core.contracts import (
    CanonicalExtractionResult,
    RawExtractionResult,
)
from document_benchmark.core.statuses import DocumentFamily
from document_benchmark.normalization.date_normalizer import normalize_date
from document_benchmark.normalization.field_mapper import detect_document_family
from document_benchmark.normalization.number_normalizer import normalize_number
from document_benchmark.normalization.tax_id_normalizer import normalize_tax_id
from document_benchmark.normalization.text_normalizer import normalize_text
from document_benchmark.schemas.invoice import InvoiceCore, InvoiceLineItem
from document_benchmark.schemas.office_supply_request import OfficeSupplyItem, OfficeSupplyRequest
from document_benchmark.schemas.software_proposal import SoftwareProposal


class CanonicalNormalizer:
    """Normalizes raw extraction results into standard business schemas."""

    def normalize(self, raw_res: RawExtractionResult) -> CanonicalExtractionResult:
        if not raw_res.success:
            return CanonicalExtractionResult(
                document_id=raw_res.document_id,
                document_family=DocumentFamily.UNKNOWN,
                canonical_payload={},
                field_evidence={},
                warnings=raw_res.warnings + [f"Raw extraction failed: {raw_res.error_message}"],
                requires_review=True,
                source_engine=raw_res.engine_id,
                source_config=raw_res.config_id,
            )

        full_text = raw_res.full_text or ""
        doc_family, doc_subtype = detect_document_family(full_text)

        candidates = raw_res.field_candidates or {}
        field_evidence: Dict[str, Any] = {}

        if doc_family == DocumentFamily.OFFICE_SUPPLY_REQUEST:
            canonical_payload, field_evidence = self._build_office_supply_payload(
                candidates, raw_res.tables, full_text
            )
        elif doc_family == DocumentFamily.SOFTWARE_PROPOSAL:
            canonical_payload, field_evidence = self._build_software_proposal_payload(
                candidates, full_text
            )
        else:
            # Default invoice
            doc_family = DocumentFamily.INVOICE
            canonical_payload, field_evidence = self._build_invoice_payload(
                candidates, raw_res.tables, full_text
            )

        return CanonicalExtractionResult(
            document_id=raw_res.document_id,
            document_family=doc_family,
            document_subtype=doc_subtype,
            canonical_payload=canonical_payload,
            field_evidence=field_evidence,
            warnings=raw_res.warnings,
            requires_review=False,
            source_engine=raw_res.engine_id,
            source_config=raw_res.config_id,
        )

    def _build_invoice_payload(
        self, candidates: Dict[str, Any], tables: List[Dict[str, Any]], full_text: str
    ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        evidence: Dict[str, Any] = {}

        def _get_norm(field_name: str, norm_fn):
            raw_v = candidates.get(field_name)
            norm_v = norm_fn(raw_v) if raw_v is not None else None
            evidence[field_name] = {"raw": raw_v, "normalized": str(norm_v) if norm_v is not None else None}
            return norm_v

        inv_num = _get_norm("invoice_number", normalize_text)
        inv_series = _get_norm("invoice_series", normalize_text)
        inv_date = _get_norm("invoice_date", normalize_date)
        seller_name = _get_norm("seller_name", normalize_text)
        seller_tax = _get_norm("seller_tax_id", normalize_tax_id)
        seller_addr = _get_norm("seller_address", normalize_text)
        buyer_name = _get_norm("buyer_name", normalize_text)
        buyer_tax = _get_norm("buyer_tax_id", normalize_tax_id)
        buyer_addr = _get_norm("buyer_address", normalize_text)
        currency = candidates.get("currency", "VND")

        subtotal = _get_norm("subtotal", normalize_number)
        discount = _get_norm("discount_amount", normalize_number) or Decimal(0)
        vat_amount = _get_norm("vat_amount", normalize_number)
        total_amount = _get_norm("total_amount", normalize_number)
        payment_method = _get_norm("payment_method", normalize_text)
        amount_in_words = _get_norm("amount_in_words", normalize_text)

        # Parse line items from extracted tables
        line_items: List[InvoiceLineItem] = []
        for tbl in tables:
            rows = tbl.get("rows", [])
            for idx, r in enumerate(rows, start=1):
                if len(r) >= 3:
                    item_desc = normalize_text(r[1]) if len(r) > 1 else None
                    unit = normalize_text(r[2]) if len(r) > 2 else None
                    qty = normalize_number(r[3]) if len(r) > 3 else None
                    price = normalize_number(r[4]) if len(r) > 4 else None
                    amt = normalize_number(r[5]) if len(r) > 5 else None

                    if item_desc or amt:
                        line_items.append(
                            InvoiceLineItem(
                                line_number=idx,
                                description=item_desc,
                                unit=unit,
                                quantity=qty,
                                unit_price=price,
                                amount_after_tax=amt,
                            )
                        )

        inv_obj = InvoiceCore(
            invoice_number=inv_num,
            invoice_series=inv_series,
            invoice_date=inv_date,
            seller_name=seller_name,
            seller_tax_id=seller_tax,
            seller_address=seller_addr,
            buyer_name=buyer_name,
            buyer_tax_id=buyer_tax,
            buyer_address=buyer_addr,
            currency=currency,
            subtotal=subtotal,
            discount_amount=discount,
            vat_amount=vat_amount,
            total_amount=total_amount,
            payment_method=payment_method,
            amount_in_words=amount_in_words,
            line_items=line_items,
        )

        return inv_obj.model_dump(mode="json"), evidence

    def _build_office_supply_payload(
        self, candidates: Dict[str, Any], tables: List[Dict[str, Any]], full_text: str
    ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        evidence: Dict[str, Any] = {}

        title = normalize_text(candidates.get("request_title"))
        req_date = normalize_date(candidates.get("request_date"))
        req_name = normalize_text(candidates.get("requester_name"))
        req_dept = normalize_text(candidates.get("requester_department"))
        total = normalize_number(candidates.get("total_amount"))

        evidence["request_title"] = {"raw": candidates.get("request_title"), "normalized": title}
        evidence["request_date"] = {"raw": candidates.get("request_date"), "normalized": req_date}

        items: List[OfficeSupplyItem] = []
        for tbl in tables:
            for idx, r in enumerate(tbl.get("rows", []), start=1):
                if len(r) >= 3:
                    desc = normalize_text(r[1]) if len(r) > 1 else None
                    unit = normalize_text(r[2]) if len(r) > 2 else None
                    qty = normalize_number(r[3]) if len(r) > 3 else None
                    price = normalize_number(r[4]) if len(r) > 4 else None
                    amt = normalize_number(r[5]) if len(r) > 5 else None

                    if desc or amt:
                        items.append(
                            OfficeSupplyItem(
                                line_number=idx,
                                description=desc,
                                unit=unit,
                                requested_quantity=qty,
                                unit_price=price,
                                amount=amt,
                            )
                        )

        req_obj = OfficeSupplyRequest(
            request_title=title,
            request_date=req_date,
            requester_name=req_name,
            requester_department=req_dept,
            total_amount=total,
            items=items,
        )
        return req_obj.model_dump(mode="json"), evidence

    def _build_software_proposal_payload(
        self, candidates: Dict[str, Any], full_text: str
    ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        evidence: Dict[str, Any] = {}

        title = normalize_text(candidates.get("proposal_title"))
        prop_date = normalize_date(candidates.get("proposal_date"))
        req_name = normalize_text(candidates.get("requester_name"))
        req_dept = normalize_text(candidates.get("requester_department"))
        sw_name = normalize_text(candidates.get("software_name"))
        supp_name = normalize_text(candidates.get("supplier_name"))
        est_cost = normalize_number(candidates.get("estimated_cost"))

        evidence["software_name"] = {"raw": candidates.get("software_name"), "normalized": sw_name}
        evidence["estimated_cost"] = {"raw": candidates.get("estimated_cost"), "normalized": str(est_cost) if est_cost else None}

        prop_obj = SoftwareProposal(
            proposal_title=title,
            proposal_date=prop_date,
            requester_name=req_name,
            requester_department=req_dept,
            software_name=sw_name,
            supplier_name=supp_name,
            estimated_cost=est_cost,
        )
        return prop_obj.model_dump(mode="json"), evidence
