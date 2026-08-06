"""Streamlit Local UI for Universal Document Engine."""

from pathlib import Path
import streamlit as st

from document_engine.export.exporter import ExcelExporter
from document_engine.orchestration.pipeline import DocumentPipeline
from document_engine.review.review_manager import ReviewManager
from document_engine.settings import get_workspace_paths
from document_engine.storage.database import DuckDBStorage


def main():
    st.set_page_config(
        page_title="Universal Document Engine",
        page_icon="📄",
        layout="wide",
    )

    st.title("📄 Universal Invoice & Business Document Engine")
    st.caption("Local-first PDF intake, inspection, parser routing, validation, and review system.")

    paths = get_workspace_paths()
    paths.ensure_directories()
    storage = DuckDBStorage(paths.database_file)
    pipeline = DocumentPipeline()
    review_mgr = ReviewManager(storage)
    exporter = ExcelExporter(storage)

    tab1, tab2, tab3, tab4, tab5 = st.tabs(
        ["1. Inbox", "2. Processing", "3. Document Detail", "4. Review Queue", "5. Export"]
    )

    with tab1:
        st.header("Local Inbox")
        file_or_folder = st.text_input("Enter local PDF path or folder path:", value=str(paths.inbox))
        path_obj = Path(file_or_folder)

        if path_obj.exists():
            if path_obj.is_file() and path_obj.suffix.lower() == ".pdf":
                st.success(f"Selected single PDF: {path_obj.name}")
                if st.button("Process Document"):
                    with st.spinner("Processing document..."):
                        res = pipeline.process_file(path_obj)
                        st.success(f"Processed Document ID: {res.document_id}")
                        st.json(res.model_dump(exclude={"envelope", "validation"}))
            elif path_obj.is_dir():
                pdfs = list(path_obj.glob("*.pdf"))
                st.info(f"Found {len(pdfs)} PDF files in directory.")
                if st.button("Process All Documents"):
                    with st.spinner("Processing batch..."):
                        summary, results = pipeline.process_folder(path_obj)
                        st.success("Batch completed!")
                        st.json(summary.model_dump())
        else:
            st.warning("Specified path does not exist.")

    with tab2:
        st.header("Processing Status & Metrics")
        with storage.get_connection() as conn:
            total_docs = conn.execute("SELECT COUNT(*) FROM documents;").fetchone()[0]
            val_docs = conn.execute("SELECT COUNT(*) FROM business_documents;").fetchone()[0]
            pending_rev = conn.execute("SELECT COUNT(*) FROM review_queue WHERE status='pending';").fetchone()[0]

        col1, col2, col3 = st.columns(3)
        col1.metric("Total Ingested", total_docs)
        col2.metric("Canonical Business Docs", val_docs)
        col3.metric("Pending Review Queue", pending_rev)

    with tab3:
        st.header("Document Detail Explorer")
        with storage.get_connection() as conn:
            docs = conn.execute("SELECT document_id, document_family, document_number FROM business_documents;").fetchall()

        if docs:
            doc_map = {f"{r[0]} ({r[1]} - {r[2] or 'No Num'})": r[0] for r in docs}
            selected_label = st.selectbox("Select Document:", list(doc_map.keys()))
            selected_id = doc_map[selected_label]

            with storage.get_connection() as conn:
                row = conn.execute(
                    "SELECT document_id, document_family, source_format, document_number, issue_date, grand_total, canonical_payload_json FROM business_documents WHERE document_id = ?;",
                    [selected_id],
                ).fetchone()

            if row:
                st.subheader(f"Document: {row[0]}")
                st.write(f"**Family:** {row[1]} | **Source Format:** {row[2]}")
                st.write(f"**Doc Number:** {row[3]} | **Issue Date:** {row[4]} | **Grand Total:** {row[5]:,.2f} VND")

                with st.expander("Canonical Payload JSON"):
                    st.code(row[6], language="json")
        else:
            st.info("No documents stored in DuckDB yet.")

    with tab4:
        st.header("Human Review Queue")
        reviews = review_mgr.list_pending_reviews()
        if reviews:
            st.warning(f"{len(reviews)} items require review.")
            rev_map = {f"{r['document_id']} ({r['reason']})": r['document_id'] for r in reviews}
            rev_id = st.selectbox("Select Item to Review:", list(rev_map.keys()))
            target_doc_id = rev_map[rev_id]

            st.subheader(f"Reviewing {target_doc_id}")
            field_name = st.text_input("Field Name to Correct (e.g. document_number):")
            new_val = st.text_input("New Corrected Value:")

            if st.button("Apply Correction"):
                if field_name and new_val:
                    corr = review_mgr.apply_correction(target_doc_id, field_name, new_val)
                    st.success(f"Correction saved! ID: {corr.correction_id}")
                    st.rerun()
        else:
            st.success("Review queue is clean!")

    with tab5:
        st.header("Excel Export Manager")
        run_id_input = st.text_input("Export Run ID:", value="latest_run")
        if st.button("Generate Multi-Sheet Excel Export"):
            out_file = paths.exports / f"document_export_{run_id_input}.xlsx"
            out_path = exporter.export_run(run_id_input, out_file)
            st.success(f"Workbook generated successfully: {out_path}")


if __name__ == "__main__":
    main()
