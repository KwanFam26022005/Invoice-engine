"""CLI interface for Document Engine using argparse."""

import argparse
from pathlib import Path
import sys
from typing import Optional

from document_engine.export.exporter import ExcelExporter
from document_engine.intake.inspector import PDFInspector
from document_engine.ir.models import generate_run_id
from document_engine.orchestration.pipeline import DocumentPipeline
from document_engine.review.review_manager import ReviewManager
from document_engine.settings import get_workspace_paths
from document_engine.storage.database import DuckDBStorage


def main(args: Optional[list] = None) -> None:
    parser = argparse.ArgumentParser(
        prog="document-engine",
        description="Universal Invoice and Business Document Processing Engine CLI",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # init-workspace
    p_init = subparsers.add_parser("init-workspace", help="Initialize workspace directories.")
    p_init.add_argument("--workspace", type=str, help="Workspace root directory path.")

    # inspect
    p_inspect = subparsers.add_parser("inspect", help="Inspect PDF document profile without OCR.")
    p_inspect.add_argument("pdf", type=str, help="Path to PDF document.")

    # process
    p_proc = subparsers.add_parser("process", help="Process a single PDF document end-to-end.")
    p_proc.add_argument("pdf", type=str, help="Path to PDF document.")
    p_proc.add_argument("--workspace", type=str, help="Workspace root directory path.")

    # process-folder
    p_folder = subparsers.add_parser("process-folder", help="Process a folder of PDF documents.")
    p_folder.add_argument("folder", type=str, help="Path to directory containing PDFs.")
    p_folder.add_argument("--workspace", type=str, help="Workspace root directory path.")

    # show
    p_show = subparsers.add_parser("show", help="Display stored document details.")
    p_show.add_argument("document_id", type=str, help="Deterministic document ID.")
    p_show.add_argument("--workspace", type=str, help="Workspace root directory path.")

    # review-list
    p_review = subparsers.add_parser("review-list", help="List items in human review queue.")
    p_review.add_argument("--workspace", type=str, help="Workspace root directory path.")

    # export
    p_export = subparsers.add_parser("export", help="Export run results to multi-sheet Excel.")
    p_export.add_argument("--run-id", type=str, default="latest", help="Processing run ID.")
    p_export.add_argument("--workspace", type=str, help="Workspace root directory path.")

    parsed = parser.parse_args(args)

    if parsed.command == "init-workspace":
        paths = get_workspace_paths(Path(parsed.workspace) if parsed.workspace else None)
        paths.ensure_directories()
        print(f"Workspace initialized successfully at: {paths.root}")

    elif parsed.command == "inspect":
        inspector = PDFInspector()
        source_doc, profile = inspector.inspect(Path(parsed.pdf))
        print(f"Document ID     : {source_doc.document_id}")
        print(f"Filename        : {source_doc.filename}")
        print(f"Page Count      : {source_doc.page_count}")
        print(f"PDF Profile     : {profile.pdf_profile.value}")
        print(f"Has Text Layer  : {profile.has_text_layer}")
        print(f"Requires OCR    : {profile.requires_ocr}")

    elif parsed.command == "process":
        pipeline = DocumentPipeline()
        res = pipeline.process_file(Path(parsed.pdf))
        print(f"Document ID       : {res.document_id}")
        print(f"PDF Profile       : {res.pdf_profile}")
        print(f"Selected Parser   : {res.selected_parser}")
        print(f"Document Family   : {res.document_family}")
        print(f"Validation Status : {res.validation_status}")
        print(f"Requires Review   : {res.requires_review}")
        print(f"Database Path     : {res.database_path}")

    elif parsed.command == "process-folder":
        pipeline = DocumentPipeline()
        summary, results = pipeline.process_folder(Path(parsed.folder))
        print(f"Received        : {summary.received}")
        print(f"Processed       : {summary.processed}")
        print(f"Accepted        : {summary.accepted}")
        print(f"Review Required : {summary.review_required}")
        print(f"Failed          : {summary.failed}")
        print(f"Unknown Family  : {summary.unknown}")

    elif parsed.command == "review-list":
        paths = get_workspace_paths(Path(parsed.workspace) if parsed.workspace else None)
        storage = DuckDBStorage(paths.database_file)
        review_mgr = ReviewManager(storage)
        items = review_mgr.list_pending_reviews()
        print(f"Pending Reviews: {len(items)}")
        for item in items:
            print(f"- [{item['status'].upper()}] ID: {item['document_id']} | Reason: {item['reason']}")

    elif parsed.command == "export":
        paths = get_workspace_paths(Path(parsed.workspace) if parsed.workspace else None)
        storage = DuckDBStorage(paths.database_file)
        exporter = ExcelExporter(storage)
        run_id = parsed.run_id if parsed.run_id != "latest" else generate_run_id()
        out_file = paths.exports / f"document_export_{run_id}.xlsx"
        export_path = exporter.export_run(run_id, out_file)
        print(f"Excel report exported to: {export_path}")

    elif parsed.command == "show":
        paths = get_workspace_paths(Path(parsed.workspace) if parsed.workspace else None)
        storage = DuckDBStorage(paths.database_file)
        with storage.get_connection() as conn:
            row = conn.execute(
                "SELECT document_id, document_family, document_number, grand_total, canonical_payload_json FROM business_documents WHERE document_id = ?;",
                [parsed.document_id],
            ).fetchone()
            if row:
                print(f"Document ID     : {row[0]}")
                print(f"Family          : {row[1]}")
                print(f"Document Number : {row[2]}")
                print(f"Grand Total     : {row[3]}")
                print(f"Payload JSON    : {row[4][:200]}...")
            else:
                print(f"Document '{parsed.document_id}' not found in database.")


if __name__ == "__main__":
    main()
