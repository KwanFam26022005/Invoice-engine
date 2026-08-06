"""Streamlit UI rendering components for single-document comparison."""

from __future__ import annotations

import csv
import json
from pathlib import Path

import streamlit as st

from document_benchmark.ui.comparison_logic import (
    extract_page_geometry_from_engine,
    generate_unified_diff,
)
from document_benchmark.ui.comparison_models import (
    DocumentInfo,
    EngineView,
    SelectedDocumentComparison,
)
from document_benchmark.ui.pdf_rendering import (
    get_pdf_base64_data_uri,
    render_pdf_page_to_png_bytes,
)


def render_no_ground_truth_banner() -> None:
    """Render mandatory fixed warning banner about no ground truth."""
    st.warning(
        "⚠️ **LƯU Ý QUAN TRỌNG**: Campaign này chưa có Ground Truth (`ground_truth_level = 0`). "
        "Các so sánh và chỉ số bên dưới **chỉ phục vụ so sánh đầu ra và hiệu năng**, không đại diện cho độ chính xác (Accuracy)."
    )


def render_header() -> None:
    """Render main header and subtitle."""
    st.title("📑 Document Engine Comparison")
    st.caption("So sánh chi tiết một tài liệu giữa **Docling OCR** (`docling_ocr_easyocr_vi_cpu`) và **PP-StructureV3** (`ppstructure_v3_vi_table_cpu`)")
    render_no_ground_truth_banner()


def render_sidebar(
    campaign_dir: Path,
    dataset_root: Path,
    document_ids: list[str],
    current_doc_id: str,
    doc_info: DocumentInfo | None,
) -> tuple[str, int, dict[str, bool]]:
    """Render sidebar control panel and return user selection controls."""
    st.sidebar.title("🛠️ Cấu hình Benchmark")

    st.sidebar.markdown(f"**Campaign Path**: `{campaign_dir}`")
    st.sidebar.markdown(f"**Dataset Root**: `{dataset_root}`")

    if doc_info and doc_info.sha256:
        st.sidebar.caption(f"SHA-256: `{doc_info.sha256[:12]}...`")

    st.sidebar.markdown("---")
    st.sidebar.subheader("📄 Chọn tài liệu benchmark")

    selected_doc_id = st.sidebar.selectbox(
        "Tài liệu Smoke (10 PDF):",
        options=document_ids,
        index=document_ids.index(current_doc_id) if current_doc_id in document_ids else 0,
    )

    if doc_info:
        st.sidebar.info(
            f"**File**: {doc_info.filename}\n\n"
            f"**Phân loại**: {doc_info.category}\n\n"
            f"**Số trang**: {doc_info.page_count}\n\n"
            f"**Input Profile**: `{doc_info.input_profile}`"
        )

    selected_page = 1
    if doc_info and doc_info.page_count > 1:
        selected_page = st.sidebar.number_input(
            "Trang hiển thị:",
            min_value=1,
            max_value=doc_info.page_count,
            value=1,
        )

    st.sidebar.markdown("---")
    st.sidebar.subheader("⚙️ Chế độ xem & Toggles")
    show_normalized = st.sidebar.checkbox("Hiển thị Normalized Text", value=False)
    ignore_diacritics = st.sidebar.checkbox("Bỏ qua dấu tiếng Việt khi so sánh", value=False)
    show_bboxes = st.sidebar.checkbox("Hiển thị Bounding Boxes", value=True)
    show_raw_json = st.sidebar.checkbox("Hiển thị Raw JSON", value=False)
    show_logs = st.sidebar.checkbox("Hiển thị Tail Logs", value=False)

    st.sidebar.markdown("---")
    if st.sidebar.button("🔄 Tải lại dữ liệu (Clear Cache)", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

    st.sidebar.caption("🔒 UI Read-only local execution. Không nạp model hay gọi API bên ngoài.")

    toggles = {
        "show_normalized": show_normalized,
        "ignore_diacritics": ignore_diacritics,
        "show_bboxes": show_bboxes,
        "show_raw_json": show_raw_json,
        "show_logs": show_logs,
    }

    return selected_doc_id, selected_page, toggles


def render_engine_summary_card(view: EngineView | None, title: str, config_id: str) -> None:
    """Render summary card for an engine configuration."""
    st.subheader(f"🔹 {title}")
    st.caption(f"Config: `{config_id}`")

    if not view:
        st.error("Không có dữ liệu trích xuất cho cấu hình này.")
        return

    col1, col2 = st.columns(2)
    with col1:
        st.markdown(f"**Trạng thái**: {'✅ SUCCESS' if view.success else '❌ FAILED'}")
        st.markdown(f"**Engine Gen**: `{view.engine_generation}`")
        st.markdown(f"**Runtime Class**: `{view.runtime_class}`")
        st.markdown(f"**OCR Engine**: `{view.ocr_engine or 'N/A'}`")
        st.markdown(f"**Ký tự văn bản**: {view.char_count:,}")
        st.markdown(f"**Số bảng trích xuất**: {view.table_count}")
        st.markdown(f"**Kích thước Raw Output**: {view.raw_json_size_bytes / 1024:.1f} KB")

    with col2:
        stats = view.performance_stats
        st.markdown(f"**Latency Trung bình (Mean)**: `{stats.extract_ms_mean:.1f} ms`")
        st.markdown(f"**Latency P50 / P95**: `{stats.extract_ms_p50:.1f} ms` / `{stats.extract_ms_p95:.1f} ms`")
        st.markdown(f"**Prepare Time**: `{stats.prepare_time_ms:.1f} ms`")
        st.markdown(f"**Peak RAM (RSS)**: `{stats.rss_peak_mb_max or 0.0:.1f} MB`")

        if not stats.cpu_metrics_valid:
            st.warning("⚠️ CPU Peak = 0.0 (metric không hợp lệ)")
        else:
            st.markdown(f"**Peak CPU**: `{stats.cpu_peak_percent_max or 0.0:.1f}%`")

    if view.provenance_mismatch:
        st.warning("⚠️ Cảnh báo không nhất quán phiên bản package giữa environment.json và runtime_metadata.")


def render_tab_overview(
    comparison: SelectedDocumentComparison,
    doc_info: DocumentInfo,
    selected_page: int,
) -> None:
    """Render Tab 1: Tổng quan (PDF Preview, Engine Cards, Latency Comparison, Speed Ratio)."""
    st.header("1. Tổng quan & Xem trước tài liệu")

    c_pdf, c_cards = st.columns([1, 1])

    with c_pdf:
        st.subheader("🖼️ PDF Gốc Preview")
        if not doc_info.pdf_available or not doc_info.resolved_pdf_path:
            st.error(f"Không thể mở file PDF: {doc_info.pdf_error}")
        else:
            pdf_path = Path(doc_info.resolved_pdf_path)
            # Try PyMuPDF page rendering
            png_bytes = render_pdf_page_to_png_bytes(pdf_path, page_number=selected_page, dpi=120)
            if png_bytes:
                st.image(png_bytes, caption=f"{doc_info.filename} - Trang {selected_page}/{doc_info.page_count}", use_container_width=True)
            else:
                # Fallback to iframe data URI
                data_uri = get_pdf_base64_data_uri(pdf_path)
                if data_uri:
                    st.components.v1.html(
                        f'<iframe src="{data_uri}" width="100%" height="500px" style="border:none;"></iframe>',
                        height=520,
                    )
                else:
                    st.error("Không thể render trang PDF.")

    with c_cards:
        col_d, col_p = st.columns(2)
        with col_d:
            render_engine_summary_card(comparison.docling_view, "Docling OCR", "docling_ocr_easyocr_vi_cpu")
        with col_p:
            render_engine_summary_card(comparison.pp_view, "PP-StructureV3", "ppstructure_v3_vi_table_cpu")

    st.markdown("---")
    st.subheader("⚡ So sánh Hiệu năng & Tỷ lệ tốc độ")

    col_speed, col_chart = st.columns([1, 2])

    with col_speed:
        if comparison.speed_ratio_mean is not None:
            st.metric(
                label="Speed Ratio (Docling Mean / PP Mean)",
                value=f"{comparison.speed_ratio_mean:.2f}x",
                delta="PP-StructureV3 nhanh hơn" if comparison.speed_ratio_mean > 1.0 else "Docling nhanh hơn",
                delta_color="normal",
            )
            st.caption("ℹ️ *Speed ratio chỉ mô tả hiệu năng xử lý, không mô tả chất lượng hay độ chính xác trích xuất.*")
        else:
            st.info("Không đủ số liệu measured repeats để tính speed ratio.")

    with col_chart:
        # Render Latency Comparison Chart using Streamlit bar chart
        chart_data = []
        if comparison.docling_view and comparison.docling_view.performance_repeats:
            for r in comparison.docling_view.performance_repeats:
                chart_data.append({"Repeat": f"Run {r.run_index}", "Engine": "Docling OCR", "Latency (ms)": r.extract_time_ms})
        if comparison.pp_view and comparison.pp_view.performance_repeats:
            for r in comparison.pp_view.performance_repeats:
                chart_data.append({"Repeat": f"Run {r.run_index}", "Engine": "PP-StructureV3", "Latency (ms)": r.extract_time_ms})

        if chart_data:
            st.caption("Bar chart: Extraction Latency qua các measured repeats (ms)")
            st.dataframe(chart_data, use_container_width=True)


def render_tab_ocr_text(comparison: SelectedDocumentComparison, toggles: dict[str, bool]) -> None:
    """Render Tab 2: Văn bản OCR (Side-by-side, Normalized, Unified Diff, Similarity)."""
    st.header("2. Văn bản trích xuất (OCR Text)")

    d_view = comparison.docling_view
    p_view = comparison.pp_view

    t_doc = d_view.full_text if d_view else ""
    t_pp = p_view.full_text if p_view else ""

    col_sim, col_mode = st.columns([1, 2])
    with col_sim:
        st.metric(
            label="Độ tương đồng mô tả (SequenceMatcher Ratio)",
            value=f"{comparison.text_similarity_ratio * 100:.2f}%",
        )
        st.caption("ℹ️ *Label: Độ tương đồng mô tả (không gọi là accuracy hay precision).*")

    with col_mode:
        mode = st.radio(
            "Chế độ hiển thị văn bản:",
            options=["Raw Side-by-Side", "Normalized Side-by-Side", "Unified Diff"],
            horizontal=True,
        )

    search_query = st.text_input("🔍 Tìm kiếm trong văn bản:", value="")

    if mode == "Unified Diff":
        st.subheader("Unified Diff giữa Docling (+) và PP-StructureV3 (-)")
        diff_str = generate_unified_diff(t_doc, t_pp, label1="Docling OCR", label2="PP-StructureV3")
        st.code(diff_str if diff_str else "Hai văn bản hoàn toàn trùng khớp.", language="diff")
    else:
        c1, c2 = st.columns(2)
        with c1:
            st.subheader("Docling OCR Text")
            st.caption(f"Độ dài: {len(t_doc):,} ký tự | {len(t_doc.split()):,} từ | {len(t_doc.splitlines()):,} dòng")
            text_to_show = t_doc
            if search_query:
                lines = [l for l in text_to_show.splitlines() if search_query.lower() in l.lower()]
                text_to_show = "\n".join(lines)
            st.text_area("Docling text", value=text_to_show, height=400, key="doc_text_area")

        with c2:
            st.subheader("PP-StructureV3 OCR Text")
            st.caption(f"Độ dài: {len(t_pp):,} ký tự | {len(t_pp.split()):,} từ | {len(t_pp.splitlines()):,} dòng")
            text_to_show_pp = t_pp
            if search_query:
                lines = [l for l in text_to_show_pp.splitlines() if search_query.lower() in l.lower()]
                text_to_show_pp = "\n".join(lines)
            st.text_area("PP text", value=text_to_show_pp, height=400, key="pp_text_area")


def render_tab_fields(comparison: SelectedDocumentComparison) -> None:
    """Render Tab 3: So sánh Field Candidates (Union of keys, normalized values, status badges)."""
    st.header("3. So sánh trường dữ liệu (Field Candidates)")

    if not comparison.field_comparisons:
        st.info("Không có trường dữ liệu field_candidates nào được ghi nhận.")
        return

    st.caption("Bảng so sánh union tất cả các trường trích xuất được từ hai engine:")

    table_data = []
    for item in comparison.field_comparisons:
        table_data.append(
            {
                "Trường dữ liệu": item.field_name,
                "Docling Raw": str(item.docling_raw) if item.docling_raw is not None else "—",
                "PP-StructureV3 Raw": str(item.pp_raw) if item.pp_raw is not None else "—",
                "Docling Normalized": str(item.docling_normalized) if item.docling_normalized else "—",
                "PP Normalized": str(item.pp_normalized) if item.pp_normalized else "—",
                "Trạng thái": item.status,
                "Bằng chứng / Ghi chú": item.evidence,
                "Cần kiểm tra": "⚠️ Cần kiểm tra thủ công" if item.requires_manual_check else "OK",
            }
        )

    st.dataframe(table_data, use_container_width=True)


def render_tab_tables(comparison: SelectedDocumentComparison) -> None:
    """Render Tab 4: So sánh Bảng (Docling headers/rows vs PP pred_html/cells)."""
    st.header("4. So sánh Bảng (Tables)")

    if not comparison.table_comparisons:
        st.info("Không phát hiện thấy bảng nào trong tài liệu này.")
        return

    st.caption(f"Tổng số bảng so sánh: {len(comparison.table_comparisons)}")

    for tbl in comparison.table_comparisons:
        with st.expander(f"📌 Bảng #{tbl.table_index + 1} (Trang {tbl.page_number}) — Structural Similarity: {tbl.structural_similarity_score * 100:.0f}%", expanded=True):
            col_m1, col_m2 = st.columns(2)
            with col_m1:
                st.markdown(f"**Docling Table**: {tbl.docling_row_count} dòng x {tbl.docling_col_count} cột")
            with col_m2:
                st.markdown(f"**PP-StructureV3 Table**: {tbl.pp_row_count} dòng x {tbl.pp_col_count} cột ({tbl.pp_cell_box_count} cell boxes)")

            c_doc_t, c_pp_t = st.columns(2)
            with c_doc_t:
                st.subheader("Docling Table Render")
                if tbl.docling_rows or tbl.docling_headers:
                    import pandas as pd
                    df_doc = pd.DataFrame(tbl.docling_rows, columns=tbl.docling_headers if tbl.docling_headers else None)
                    st.dataframe(df_doc, use_container_width=True)
                else:
                    st.info("Docling không có dữ liệu bảng này.")

            with c_pp_t:
                st.subheader("PP-StructureV3 Table Render")
                if tbl.pp_parsed_rows or tbl.pp_parsed_headers:
                    import pandas as pd
                    df_pp = pd.DataFrame(tbl.pp_parsed_rows, columns=tbl.pp_parsed_headers if tbl.pp_parsed_headers else None)
                    st.dataframe(df_pp, use_container_width=True)
                elif tbl.pp_pred_html:
                    st.code(tbl.pp_pred_html, language="html")
                else:
                    st.info("PP-StructureV3 không có dữ liệu bảng này.")


def render_tab_geometry(
    comparison: SelectedDocumentComparison,
    doc_info: DocumentInfo,
    selected_page: int,
) -> None:
    """Render Tab 5: Geometry Bounding Boxes Overlay."""
    st.header("5. Bố cục & Bounding Boxes Geometry")

    if not doc_info.pdf_available or not doc_info.resolved_pdf_path:
        st.error("Không thể render geometry vì thiếu file PDF gốc.")
        return

    pp_geom_dict = extract_page_geometry_from_engine(comparison.pp_view)
    pg_geom = pp_geom_dict.get(selected_page)

    if not pg_geom or not pg_geom.boxes:
        st.info("Tài liệu hiện tại không chứa dữ liệu bounding box geometry khả thi hoặc chưa xác định được hệ tọa độ.")
        return

    st.markdown(f"**PP-StructureV3 Geometry Boxes (Trang {selected_page})**: {len(pg_geom.boxes)} bounding boxes")

    boxes_summary = []
    for idx, b in enumerate(pg_geom.boxes[:30]):
        boxes_summary.append({
            "Index": idx + 1,
            "Type": b.box_type,
            "Label": b.label,
            "Score": f"{b.score:.2f}" if b.score else "N/A",
            "Coordinate [xmin, ymin, xmax, ymax]": str([round(x, 1) for x in b.box]),
        })

    st.dataframe(boxes_summary, use_container_width=True)


def render_tab_performance(comparison: SelectedDocumentComparison) -> None:
    """Render Tab 6: Hiệu năng & Tài nguyên chi tiết."""
    st.header("6. Chi tiết Hiệu năng & Tài nguyên (Performance & Resources)")

    col1, col2 = st.columns(2)

    with col1:
        st.subheader("Docling OCR Measured Repeats")
        if comparison.docling_view and comparison.docling_view.performance_repeats:
            st.dataframe(
                [
                    {
                        "Run Index": r.run_index,
                        "Status": r.status,
                        "Extract ms": r.extract_time_ms,
                        "Total Pipeline ms": r.total_pipeline_ms,
                        "RSS Peak MB": r.rss_peak_mb or "N/A",
                        "CPU Peak %": r.cpu_peak_percent if r.cpu_peak_percent is not None else "N/A",
                    }
                    for r in comparison.docling_view.performance_repeats
                ],
                use_container_width=True,
            )

    with col2:
        st.subheader("PP-StructureV3 Measured Repeats")
        if comparison.pp_view and comparison.pp_view.performance_repeats:
            st.dataframe(
                [
                    {
                        "Run Index": r.run_index,
                        "Status": r.status,
                        "Extract ms": r.extract_time_ms,
                        "Total Pipeline ms": r.total_pipeline_ms,
                        "RSS Peak MB": r.rss_peak_mb or "N/A",
                        "CPU Peak %": r.cpu_peak_percent if r.cpu_peak_percent is not None else "N/A",
                    }
                    for r in comparison.pp_view.performance_repeats
                ],
                use_container_width=True,
            )


def render_tab_diagnostics(comparison: SelectedDocumentComparison) -> None:
    """Render Tab 7: Provenance, Logs, Warnings, Raw JSON."""
    st.header("7. Chẩn đoán & Raw Metadata Provenance")

    d_view = comparison.docling_view
    p_view = comparison.pp_view

    if (d_view and d_view.provenance_mismatch) or (p_view and p_view.provenance_mismatch):
        st.warning("⚠️ **Phát hiện Mismatch Provenance**: Phiên bản package giữa `environment.json` và `runtime_metadata` có sự không nhất quán.")

    c1, c2 = st.columns(2)

    with c1:
        st.subheader("Docling OCR Diagnostics")
        if d_view:
            st.json(
                {
                    "runtime_class": d_view.runtime_class,
                    "engine_generation": d_view.engine_generation,
                    "package_versions_runtime": d_view.package_versions_runtime,
                    "package_versions_env": d_view.package_versions_env,
                    "warnings": d_view.warnings,
                    "raw_result_path": d_view.raw_result_path,
                }
            )

    with c2:
        st.subheader("PP-StructureV3 Diagnostics")
        if p_view:
            st.json(
                {
                    "runtime_class": p_view.runtime_class,
                    "engine_generation": p_view.engine_generation,
                    "package_versions_runtime": p_view.package_versions_runtime,
                    "package_versions_env": p_view.package_versions_env,
                    "warnings": p_view.warnings,
                    "raw_result_path": p_view.raw_result_path,
                }
            )


def render_downloads_section(comparison: SelectedDocumentComparison) -> None:
    """Render download buttons for extracted texts, field CSV, and json comparisons."""
    st.markdown("---")
    st.subheader("📥 Export & Download dữ liệu tài liệu")

    c1, c2, c3, c4 = st.columns(4)

    if comparison.docling_view:
        with c1:
            st.download_button(
                label="📄 Docling Text (.txt)",
                data=comparison.docling_view.full_text.encode("utf-8"),
                file_name=f"{comparison.document.document_id}_docling.txt",
                mime="text/plain",
            )
    if comparison.pp_view:
        with c2:
            st.download_button(
                label="📄 PP Text (.txt)",
                data=comparison.pp_view.full_text.encode("utf-8"),
                file_name=f"{comparison.document.document_id}_ppstructure.txt",
                mime="text/plain",
            )

    with c3:
        if comparison.field_comparisons:
            import io
            csv_buf = io.StringIO()
            writer = csv.DictWriter(csv_buf, fieldnames=["field_name", "docling_raw", "pp_raw", "docling_normalized", "pp_normalized", "status", "evidence"])
            writer.writeheader()
            for f_item in comparison.field_comparisons:
                writer.writerow({
                    "field_name": f_item.field_name,
                    "docling_raw": f_item.docling_raw,
                    "pp_raw": f_item.pp_raw,
                    "docling_normalized": f_item.docling_normalized,
                    "pp_normalized": f_item.pp_normalized,
                    "status": f_item.status,
                    "evidence": f_item.evidence,
                })
            st.download_button(
                label="📊 Field Comparison (.csv)",
                data=csv_buf.getvalue().encode("utf-8"),
                file_name=f"{comparison.document.document_id}_fields.csv",
                mime="text/csv",
            )

    with c4:
        summary_dict = {
            "document_id": comparison.document.document_id,
            "filename": comparison.document.filename,
            "text_similarity_ratio": comparison.text_similarity_ratio,
            "speed_ratio_mean": comparison.speed_ratio_mean,
        }
        st.download_button(
            label="💾 Summary JSON",
            data=json.dumps(summary_dict, indent=2, ensure_ascii=False).encode("utf-8"),
            file_name=f"{comparison.document.document_id}_comparison.json",
            mime="application/json",
        )
