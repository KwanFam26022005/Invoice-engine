"""Cross-engine disagreement analysis and consensus builder."""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict

from document_benchmark.core.contracts import CanonicalExtractionResult
from document_benchmark.core.statuses import Severity


class FieldComparisonRow(BaseModel):
    """Row representing field comparison across engine extractions."""

    model_config = ConfigDict(extra="ignore")

    document_id: str
    field_path: str
    engine_values: Dict[str, Any]  # config_id -> normalized_value
    consensus_value: Optional[Any] = None
    agreement_count: int = 0
    total_engines: int = 0
    disagreement_severity: Severity = Severity.INFO


def compute_cross_engine_disagreement(
    document_id: str, results: List[CanonicalExtractionResult]
) -> List[FieldComparisonRow]:
    """Compute consensus and disagreement severity across engines for a document."""
    if not results:
        return []

    priority_fields = {
        "invoice_number": Severity.CRITICAL,
        "invoice_date": Severity.HIGH,
        "seller_tax_id": Severity.CRITICAL,
        "buyer_tax_id": Severity.HIGH,
        "subtotal": Severity.CRITICAL,
        "vat_amount": Severity.CRITICAL,
        "total_amount": Severity.CRITICAL,
        "software_name": Severity.HIGH,
        "estimated_cost": Severity.HIGH,
    }

    # Collect all field paths
    all_fields = set()
    for res in results:
        all_fields.update(res.canonical_payload.keys())

    comparison_rows: List[FieldComparisonRow] = []

    for f_path in sorted(all_fields):
        engine_vals: Dict[str, Any] = {}
        val_counts: Dict[str, int] = {}

        for res in results:
            cfg_id = res.source_config or res.source_engine
            val = res.canonical_payload.get(f_path)
            str_val = str(val) if val is not None else None
            engine_vals[cfg_id] = str_val

            if str_val is not None:
                val_counts[str_val] = val_counts.get(str_val, 0) + 1

        total_engines = len(results)
        if not val_counts:
            consensus_val = None
            max_agree = 0
        else:
            # Find majority value
            consensus_val, max_agree = max(val_counts.items(), key=lambda x: x[1])

        # Disagreement severity logic
        if max_agree == total_engines:
            severity = Severity.INFO
        elif max_agree > 1:
            severity = priority_fields.get(f_path, Severity.WARNING)
        else:
            severity = priority_fields.get(f_path, Severity.ERROR)

        comparison_rows.append(
            FieldComparisonRow(
                document_id=document_id,
                field_path=f_path,
                engine_values=engine_vals,
                consensus_value=consensus_val,
                agreement_count=max_agree,
                total_engines=total_engines,
                disagreement_severity=severity,
            )
        )

    return comparison_rows
