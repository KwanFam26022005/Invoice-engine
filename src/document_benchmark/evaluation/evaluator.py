"""Evaluator computing metrics against Ground Truth Level 0, Level 1, and Level 2."""

from decimal import Decimal
from typing import Any, Dict, Optional
from pydantic import BaseModel, ConfigDict

from document_benchmark.core.contracts import CanonicalExtractionResult


class GroundTruthMetrics(BaseModel):
    """Evaluation metrics comparing canonical extraction against ground truth."""

    model_config = ConfigDict(extra="ignore")

    config_id: str
    document_id: str
    ground_truth_level: int = 0
    critical_field_accuracy: float = 0.0
    field_precision: float = 0.0
    field_recall: float = 0.0
    field_f1: float = 0.0
    line_item_f1: float = 0.0
    aggregation_error_absolute: Optional[Decimal] = None
    aggregation_error_relative: Optional[float] = None


class Evaluator:
    """Evaluates canonical extraction results against Ground Truth JSON."""

    def evaluate_result(
        self,
        canonical: CanonicalExtractionResult,
        ground_truth: Dict[str, Any],
        gt_level: int = 1,
    ) -> GroundTruthMetrics:
        config_id = canonical.source_config or canonical.source_engine
        doc_id = canonical.document_id

        gt_fields = ground_truth.get("canonical_payload", ground_truth)
        can_fields = canonical.canonical_payload or {}

        critical_keys = [
            "invoice_number",
            "invoice_date",
            "seller_tax_id",
            "subtotal",
            "vat_amount",
            "total_amount",
        ]

        # 1. Critical Field Accuracy
        matched_crit = 0
        total_crit = 0
        for k in critical_keys:
            if k in gt_fields:
                total_crit += 1
                gt_val = str(gt_fields.get(k)).strip() if gt_fields.get(k) is not None else None
                can_val = str(can_fields.get(k)).strip() if can_fields.get(k) is not None else None
                if gt_val == can_val and gt_val is not None:
                    matched_crit += 1

        crit_acc = (matched_crit / total_crit) if total_crit > 0 else 1.0

        # 2. Overall Field Precision, Recall, F1
        tp = 0
        fp = 0
        fn = 0
        for k, gt_v in gt_fields.items():
            if k == "line_items" or k == "items":
                continue
            can_v = can_fields.get(k)
            gt_str = str(gt_v).strip() if gt_v is not None else None
            can_str = str(can_v).strip() if can_v is not None else None

            if gt_str is not None and can_str is not None:
                if gt_str == can_str:
                    tp += 1
                else:
                    fp += 1
                    fn += 1
            elif gt_str is not None and can_str is None:
                fn += 1
            elif gt_str is None and can_str is not None:
                fp += 1

        precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) > 0 else 0.0

        # 3. Relative Aggregation Error
        abs_err = None
        rel_err = None
        if "total_amount" in gt_fields and "total_amount" in can_fields:
            try:
                gt_tot = Decimal(str(gt_fields["total_amount"]))
                can_tot = Decimal(str(can_fields["total_amount"])) if can_fields["total_amount"] is not None else Decimal(0)
                abs_err = abs(can_tot - gt_tot)
                if gt_tot != Decimal(0):
                    rel_err = float(abs_err / abs(gt_tot))
                else:
                    rel_err = float(abs_err)
            except Exception:
                pass

        return GroundTruthMetrics(
            config_id=config_id,
            document_id=doc_id,
            ground_truth_level=gt_level,
            critical_field_accuracy=round(crit_acc, 4),
            field_precision=round(precision, 4),
            field_recall=round(recall, 4),
            field_f1=round(f1, 4),
            aggregation_error_absolute=abs_err,
            aggregation_error_relative=round(rel_err, 4) if rel_err is not None else None,
        )
