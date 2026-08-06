"""Streamlit UI Application for Document Engine Benchmark."""

import hashlib
import json
from pathlib import Path
import tempfile
import uuid
from datetime import datetime, timezone

import streamlit as st

from document_benchmark.aggregation.duckdb_engine import DuckDBAggregator
from document_benchmark.core.contracts import BenchmarkRunSpec, DocumentInput
from document_benchmark.core.engine_registry import registry
from document_benchmark.evaluation.disagreement import compute_cross_engine_disagreement
from document_benchmark.export.excel_writer import ExcelWriter
from document_benchmark.normalization.canonical_normalizer import CanonicalNormalizer
from document_benchmark.runner.benchmark_controller import BenchmarkController
from document_benchmark.storage.run_store import RunStore
from document_benchmark.validation.validation_runner import ValidationRunner


def compute_sha256_bytes(b_data: bytes) -> str:
    return hashlib.sha256(b_data).hexdigest()


def get_pdf_page_count_bytes(b_data: bytes) -> int:
    try:
        from pypdf import PdfReader
        import io
        reader = PdfReader(io.BytesIO(b_data))
        return len(reader.pages)
    except Exception:
        return 1


def load_yaml_configs() -> None:
    configs_dir = Path("configs/engines")
    if configs_dir.exists():
        for f in configs_dir.glob("*.yaml"):
            try:
                registry.load_config_from_file(str(f))
            except Exception:
                pass


def main() -> None:
    st.set_page_config(
        page_title="Document Extraction Engine Benchmark",
        page_icon="📑",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    load_yaml_configs()

    st.title("📑 Document Extraction Engine Benchmark Platform")
    st.markdown(
        "Local-first benchmarking platform for Vietnamese logistics document extraction engines."
    )

    tabs = st.tabs([
        "📤 1. Upload & Configure",
        "⚡ 2. Benchmark Progress & Runs",
        "🔍 3. Per-Document Comparison",
        "🏆 4. Engine Leaderboard",
        "📊 5. Financial Aggregation",
        "📥 6. Excel Export",
    ])

    if "current_run_summary" not in st.session_state:
        st.session_state["current_run_summary"] = None
    if "reviewed_results" not in st.session_state:
        st.session_state["reviewed_results"] = {}

    # TAB 1: Upload & Configure
    with tabs[0]:
        st.header("1. Upload Documents & Configure Benchmark")
        col_up, col_cfg = st.columns([1, 1])

        with col_up:
            uploaded_files = st.file_uploader(
                "Upload PDF Documents", type=["pdf"], accept_multiple_files=True
            )
            doc_inputs: list[DocumentInput] = []

            if uploaded_files:
                st.subheader(f"Uploaded Files ({len(uploaded_files)})")
                temp_upload_dir = Path(tempfile.gettempdir()) / "doc_bm_uploads"
                temp_upload_dir.mkdir(parents=True, exist_ok=True)

                for f in uploaded_files:
                    content = f.read()
                    sha = compute_sha256_bytes(content)
                    pgs = get_pdf_page_count_bytes(content)
                    saved_path = temp_upload_dir / f.name
                    with open(saved_path, "wb") as out_f:
                        out_f.write(content)

                    doc_inputs.append(
                        DocumentInput(
                            document_id=f"doc_{Path(f.name).stem}_{sha[:6]}",
                            path=str(saved_path.resolve()),
                            filename=f.name,
                            sha256=sha,
                            page_count=pgs,
                        )
                    )

                st.dataframe(
                    [
                        {
                            "Filename": d.filename,
                            "Pages": d.page_count,
                            "SHA-256": d.sha256[:12] + "...",
                            "Path": d.path,
                        }
                        for d in doc_inputs
                    ],
                    use_container_width=True,
                )

        with col_cfg:
            st.subheader("Benchmark Execution Settings")
            available_configs = registry.list_configs()

            config_options = {}
            for c in available_configs:
                health = registry.healthcheck_config(c.config_id)
                status_str = "AVAILABLE" if health.available else f"UNAVAILABLE ({health.error_message})"
                config_options[c.config_id] = f"{c.config_id} [{status_str}]"

            selected_config_ids = st.multiselect(
                "Select Engine Configurations",
                options=list(config_options.keys()),
                default=["mock_default", "docling_text_only_cpu"] if "docling_text_only_cpu" in config_options else ["mock_default"],
                format_func=lambda x: config_options[x],
            )

            execution_mode = st.selectbox(
                "Execution Mode", options=["both", "correctness", "performance"]
            )

            col_sub1, col_sub2 = st.columns(2)
            with col_sub1:
                warmup_runs = st.number_input("Warmup Runs", min_value=0, max_value=5, value=1)
                timeout_sec = st.number_input("Timeout (seconds)", min_value=10, max_value=600, value=120)
            with col_sub2:
                measured_runs = st.number_input("Measured Runs", min_value=1, max_value=10, value=2)
                sampling_ms = st.number_input("Resource Sample (ms)", min_value=50, max_value=1000, value=200)

            if st.button("🚀 Start Benchmark Execution", type="primary", use_container_width=True):
                if not doc_inputs:
                    st.error("Please upload at least one PDF document.")
                elif not selected_config_ids:
                    st.error("Please select at least one engine configuration.")
                else:
                    run_id = f"run_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
                    run_spec = BenchmarkRunSpec(
                        run_id=run_id,
                        document_ids=[d.document_id for d in doc_inputs],
                        engine_config_ids=selected_config_ids,
                        execution_mode=execution_mode,
                        timeout_seconds=timeout_sec,
                        warmup_runs=warmup_runs,
                        measured_runs=measured_runs,
                        resource_sample_interval_ms=sampling_ms,
                    )

                    st.session_state["active_run_spec"] = run_spec
                    st.session_state["active_documents"] = doc_inputs
                    st.success(f"Benchmark run initialized: {run_id}. Switch to Tab 2 to execute.")

    # TAB 2: Run Progress & Execution
    with tabs[1]:
        st.header("2. Benchmark Execution Progress")
        if "active_run_spec" in st.session_state:
            run_spec: BenchmarkRunSpec = st.session_state["active_run_spec"]
            documents: list[DocumentInput] = st.session_state["active_documents"]

            st.info(f"Run ID: {run_spec.run_id} | Documents: {len(documents)} | Engines: {len(run_spec.engine_config_ids)}")

            if st.button("▶ Run Active Benchmark", type="primary"):
                controller = BenchmarkController()
                progress_bar = st.progress(0.0)
                status_text = st.empty()

                total_tasks = len(documents) * len(run_spec.engine_config_ids) * (run_spec.warmup_runs + run_spec.measured_runs)
                current_task = [0]

                def on_progress(p_info):
                    current_task[0] += 1
                    pct = min(1.0, current_task[0] / max(1, total_tasks))
                    progress_bar.progress(pct)
                    status_text.markdown(
                        f"Running **{p_info['config_id']}** on **{p_info['filename']}** (Run {p_info['run_index']}, Warmup={p_info['is_warmup']})"
                    )

                summary = controller.run_benchmark(
                    spec=run_spec,
                    documents=documents,
                    progress_callback=on_progress,
                )

                st.session_state["current_run_summary"] = summary
                st.success("Benchmark completed successfully!")
                st.json(summary)
        else:
            st.info("No active benchmark configured. Please configure and start in Tab 1.")

    # TAB 3: Per-Document Comparison
    with tabs[2]:
        st.header("3. Per-Document Extraction & Field Comparison")
        if st.session_state["current_run_summary"]:
            summary = st.session_state["current_run_summary"]
            run_id = summary["run_id"]
            store = RunStore()
            paths = store.get_paths(run_id)

            # Load canonical outputs
            normalizer = CanonicalNormalizer()
            validator = ValidationRunner()

            canonical_results = []
            validation_issues = []

            for res in summary.get("results", []):
                if res.get("raw_result"):
                    from document_benchmark.core.contracts import RawExtractionResult
                    raw_res = RawExtractionResult(**res["raw_result"])
                    can = normalizer.normalize(raw_res)
                    issues = validator.validate(can)

                    canonical_results.append(can)
                    validation_issues.extend([i.model_dump() for i in issues])

            st.subheader("Field Disagreement Analysis")
            doc_ids = list({c.document_id for c in canonical_results})
            selected_doc_id = st.selectbox("Select Document", options=doc_ids)

            if selected_doc_id:
                doc_canonicals = [c for c in canonical_results if c.document_id == selected_doc_id]
                disagreements = compute_cross_engine_disagreement(selected_doc_id, doc_canonicals)

                st.dataframe(
                    [
                        {
                            "Field Path": d.field_path,
                            "Consensus Value": d.consensus_value,
                            "Agreement Count": f"{d.agreement_count}/{d.total_engines}",
                            "Disagreement Severity": d.disagreement_severity.value,
                            "Engine Values": json.dumps(d.engine_values, ensure_ascii=False),
                        }
                        for d in disagreements
                    ],
                    use_container_width=True,
                )

    # TAB 4: Engine Leaderboard
    with tabs[3]:
        st.header("4. Engine Benchmark Leaderboard")
        if st.session_state["current_run_summary"]:
            summary = st.session_state["current_run_summary"]
            results = summary.get("results", [])

            agg_stats = {}
            for r in results:
                cfg = r["config_id"]
                if cfg not in agg_stats:
                    agg_stats[cfg] = {"runs": 0, "success": 0, "latencies": [], "rss_peaks": []}
                agg_stats[cfg]["runs"] += 1
                if r.get("success"):
                    agg_stats[cfg]["success"] += 1
                if r.get("total_pipeline_ms"):
                    agg_stats[cfg]["latencies"].append(r["total_pipeline_ms"])
                rs = r.get("resource_summary", {})
                if rs.get("rss_peak_mb"):
                    agg_stats[cfg]["rss_peaks"].append(rs["rss_peak_mb"])

            leaderboard_data = []
            for cfg, data in agg_stats.items():
                lats = data["latencies"]
                rss = data["rss_peaks"]
                leaderboard_data.append(
                    {
                        "Engine Config": cfg,
                        "Success Rate": f"{(data['success']/data['runs'])*100:.1f}%",
                        "Mean Latency (ms)": f"{sum(lats)/len(lats):.2f}" if lats else "N/A",
                        "P50 Latency (ms)": f"{sorted(lats)[len(lats)//2]:.2f}" if lats else "N/A",
                        "Peak RAM (MB)": f"{max(rss):.2f}" if rss else "N/A",
                    }
                )

            st.dataframe(leaderboard_data, use_container_width=True)

    # TAB 5: Aggregation Analytics
    with tabs[4]:
        st.header("5. Financial Aggregation & Analytics")
        if st.session_state["current_run_summary"]:
            agg = DuckDBAggregator()
            # Query financial totals
            totals = agg.query_engine_financial_totals()
            st.subheader("Financial Totals by Engine")
            st.dataframe(totals, use_container_width=True)
            agg.close()

    # TAB 6: Excel Export
    with tabs[5]:
        st.header("6. Export Excel Reports")
        if st.session_state["current_run_summary"]:
            summary = st.session_state["current_run_summary"]
            run_id = summary["run_id"]
            store = RunStore()
            paths = store.get_paths(run_id)

            writer = ExcelWriter()
            report_file = paths.reports_dir / f"benchmark_report_{run_id}.xlsx"
            writer.write_benchmark_report(
                output_path=report_file,
                run_info={"run_id": run_id, "timestamp": datetime.now(timezone.utc).isoformat()},
                documents=[{"document_id": d.document_id, "filename": d.filename, "page_count": d.page_count, "sha256": d.sha256, "document_family": "invoice"} for d in st.session_state.get("active_documents", [])],
                engine_summary=[{"config_id": "mock_default", "doc_count": 1, "total_subtotal": 10000000, "total_vat": 1000000, "total_amount": 11000000}],
                field_comparisons=[],
                latency_metrics=[],
                validation_issues=[],
            )

            st.success(f"Report generated: {report_file}")
            with open(report_file, "rb") as f:
                st.download_button(
                    label="📥 Download Benchmark Report XLSX",
                    data=f.read(),
                    file_name=report_file.name,
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )


if __name__ == "__main__":
    main()
