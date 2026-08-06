"""Standalone Streamlit application for single-document engine comparison."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import streamlit as st

from document_benchmark.ui.comparison_components import (
    render_downloads_section,
    render_header,
    render_sidebar,
    render_tab_diagnostics,
    render_tab_fields,
    render_tab_geometry,
    render_tab_ocr_text,
    render_tab_overview,
    render_tab_performance,
    render_tab_tables,
)
from document_benchmark.ui.comparison_loader import (
    load_campaign_json,
    load_correctness_index,
    load_document_info,
    load_document_runs_csv,
    load_engine_view_for_document,
)
from document_benchmark.ui.comparison_logic import (
    build_selected_document_comparison,
)
from document_benchmark.ui.comparison_models import SelectedDocumentComparison


def parse_cli_args() -> tuple[Path, Path]:
    """Parse --campaign-dir and --dataset-root arguments if passed."""
    default_campaign = Path(r"D:\Documents-engine\runs\smoke\smoke_scan_baseline_001")
    default_dataset = Path(r"D:\Documents-engine\datasets")

    # If running inside Streamlit with '--', inspect sys.argv
    args_list = sys.argv[1:]
    if "--" in args_list:
        idx = args_list.index("--")
        args_list = args_list[idx + 1 :]

    parser = argparse.ArgumentParser(description="Run single-document engine comparison UI")
    parser.add_argument("--campaign-dir", type=str, default=str(default_campaign))
    parser.add_argument("--dataset-root", type=str, default=str(default_dataset))

    try:
        known, _ = parser.parse_known_args(args_list)
        c_dir = Path(known.campaign_dir)
        d_root = Path(known.dataset_root)
        if c_dir.exists():
            default_campaign = c_dir
        if d_root.exists():
            default_dataset = d_root
    except Exception:
        pass

    return default_campaign, default_dataset


def run_comparison_app() -> None:
    """Main Streamlit app entrypoint."""
    st.set_page_config(
        page_title="Single-Document Engine Comparison",
        page_icon="📑",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    default_campaign, default_dataset = parse_cli_args()

    # Sidebar inputs for paths
    campaign_dir_input = st.sidebar.text_input("Campaign Directory:", value=str(default_campaign))
    dataset_root_input = st.sidebar.text_input("Dataset Root:", value=str(default_dataset))

    campaign_dir = Path(campaign_dir_input)
    dataset_root = Path(dataset_root_input)

    if not campaign_dir.exists():
        st.error(f"Thư mục Campaign không tồn tại: `{campaign_dir}`")
        return

    try:
        campaign_json = load_campaign_json(campaign_dir)
    except Exception as exc:
        st.error(f"Không thể đọc `campaign.json`: {exc}")
        return

    correctness_rows = load_correctness_index(campaign_dir)
    document_runs_rows = load_document_runs_csv(campaign_dir)

    # Document IDs list in campaign order
    document_ids = [d.get("document_id") for d in campaign_json.get("documents", []) if d.get("document_id")]
    if not document_ids:
        st.error("Campaign không chứa danh sách tài liệu hợp lệ.")
        return

    # Selected document from sidebar
    current_doc_id = document_ids[0]
    if "selected_doc_id" in st.session_state and st.session_state["selected_doc_id"] in document_ids:
        current_doc_id = st.session_state["selected_doc_id"]

    doc_info = load_document_info(dataset_root, campaign_json, current_doc_id)

    selected_doc_id, selected_page, toggles = render_sidebar(
        campaign_dir=campaign_dir,
        dataset_root=dataset_root,
        document_ids=document_ids,
        current_doc_id=current_doc_id,
        doc_info=doc_info,
    )

    if selected_doc_id != current_doc_id:
        st.session_state["selected_doc_id"] = selected_doc_id
        doc_info = load_document_info(dataset_root, campaign_json, selected_doc_id)

    # Load EngineViews for both configs
    docling_view = load_engine_view_for_document(
        campaign_dir=campaign_dir,
        campaign_json=campaign_json,
        correctness_rows=correctness_rows,
        document_runs_rows=document_runs_rows,
        config_id="docling_ocr_easyocr_vi_cpu",
        document_id=selected_doc_id,
    )

    pp_view = load_engine_view_for_document(
        campaign_dir=campaign_dir,
        campaign_json=campaign_json,
        correctness_rows=correctness_rows,
        document_runs_rows=document_runs_rows,
        config_id="ppstructure_v3_vi_table_cpu",
        document_id=selected_doc_id,
    )

    sim_ratio, field_items, table_items, speed_ratio = build_selected_document_comparison(
        docling_view=docling_view,
        pp_view=pp_view,
        ignore_diacritics=toggles["ignore_diacritics"],
    )

    comparison = SelectedDocumentComparison(
        document=doc_info,
        docling_view=docling_view,
        pp_view=pp_view,
        text_similarity_ratio=sim_ratio,
        field_comparisons=field_items,
        table_comparisons=table_items,
        speed_ratio_mean=speed_ratio,
        campaign_id=campaign_json.get("campaign_id", ""),
        dataset_fingerprint=campaign_json.get("dataset_fingerprint", ""),
    )

    render_header()

    # Create 7 Tabs
    tabs = st.tabs([
        "📊 1. Tổng quan",
        "🔤 2. Văn bản OCR",
        "📋 3. Trường dữ liệu",
        "📐 4. Bảng",
        "📍 5. Bố cục",
        "⚡ 6. Hiệu năng",
        "🔍 7. Chẩn đoán",
    ])

    with tabs[0]:
        render_tab_overview(comparison, doc_info, selected_page)

    with tabs[1]:
        render_tab_ocr_text(comparison, toggles)

    with tabs[2]:
        render_tab_fields(comparison)

    with tabs[3]:
        render_tab_tables(comparison)

    with tabs[4]:
        render_tab_geometry(comparison, doc_info, selected_page)

    with tabs[5]:
        render_tab_performance(comparison)

    with tabs[6]:
        render_tab_diagnostics(comparison)

    render_downloads_section(comparison)


if __name__ == "__main__":
    run_comparison_app()
