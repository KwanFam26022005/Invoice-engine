"""Unit tests for comparison_loader module."""

from pathlib import Path
import pytest

from document_benchmark.ui.comparison_loader import (
    load_campaign_json,
    load_correctness_index,
    load_document_runs_csv,
    load_engine_view_for_document,
    validate_path_containment,
)


def test_validate_path_containment_valid(tmp_path: Path) -> None:
    base = tmp_path / "base"
    base.mkdir()
    child = base / "sub" / "file.txt"
    child.parent.mkdir()
    child.write_text("hello", encoding="utf-8")

    resolved = validate_path_containment(base, child)
    assert resolved == child.resolve()


def test_validate_path_containment_rejects_traversal(tmp_path: Path) -> None:
    base = tmp_path / "base"
    base.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("secret", encoding="utf-8")

    with pytest.raises(ValueError, match="Path containment violation"):
        validate_path_containment(base, base / ".." / "outside.txt")


def test_real_campaign_loading() -> None:
    camp_dir = Path(r"D:\Documents-engine\runs\smoke\smoke_scan_baseline_001")
    dataset_root = Path(r"D:\Documents-engine\datasets")

    if not camp_dir.exists():
        pytest.skip("Real campaign smoke_scan_baseline_001 not present.")

    camp_json = load_campaign_json(camp_dir)
    assert camp_json["campaign_id"] == "smoke_scan_baseline_001"
    assert camp_json["dataset_fingerprint"] == "623bc943d81c98539cef92b5b9c935aef240edb04c6c85c2906503d2450b9468"

    doc_ids = [d["document_id"] for d in camp_json["documents"]]
    assert len(doc_ids) == 10
    expected_order = [
        "VATD-0001", "VATD-0002", "UTIL-0001", "UTIL-0002", "UTIL-0003",
        "SALE-0001", "SALE-0002", "SALE-0003", "SALE-0004", "SALE-0005"
    ]
    assert doc_ids == expected_order

    c_rows = load_correctness_index(camp_dir)
    assert len(c_rows) == 20

    dr_rows = load_document_runs_csv(camp_dir)
    assert len(dr_rows) == 60  # 10 docs * 2 configs * 3 measured runs

    # Test loading engine view for SALE-0001
    d_view = load_engine_view_for_document(
        campaign_dir=camp_dir,
        campaign_json=camp_json,
        correctness_rows=c_rows,
        document_runs_rows=dr_rows,
        config_id="docling_ocr_easyocr_vi_cpu",
        document_id="SALE-0001",
    )
    assert d_view is not None
    assert d_view.success is True
    assert d_view.char_count > 0
    assert d_view.performance_stats.measured_count == 3

    p_view = load_engine_view_for_document(
        campaign_dir=camp_dir,
        campaign_json=camp_json,
        correctness_rows=c_rows,
        document_runs_rows=dr_rows,
        config_id="ppstructure_v3_vi_table_cpu",
        document_id="SALE-0001",
    )
    assert p_view is not None
    assert p_view.success is True
    assert p_view.char_count > 0
    assert p_view.performance_stats.measured_count == 3
