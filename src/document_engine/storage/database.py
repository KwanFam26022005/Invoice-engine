"""DuckDB storage engine with idempotent schema migrations, canonical versioning, and isolated document transactions."""

from pathlib import Path
from typing import Optional
import duckdb

from document_engine.extraction.candidate import FamilyCompletenessReport
from document_engine.ir.models import SourceDocument
from document_engine.routing.parser_router import ParserRoutingOutcome, RoutingDecision
from document_engine.schemas.family_schemas import BusinessDocumentEnvelope
from document_engine.storage.projector import RelationalProjector
from document_engine.validation.validator import ValidationResult


class DuckDBStorage:
    def __init__(self, db_path: Path):
        self.db_path = Path(db_path).resolve()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.projector = RelationalProjector()
        self.init_schema()

    def get_connection(self) -> duckdb.DuckDBPyConnection:
        return duckdb.connect(str(self.db_path))

    def init_schema(self) -> None:
        """Run idempotent DDL migrations."""
        with self.get_connection() as conn:
            conn.execute("""
            CREATE TABLE IF NOT EXISTS documents (
                document_id VARCHAR PRIMARY KEY,
                filename VARCHAR,
                path VARCHAR,
                mime_type VARCHAR,
                sha256 VARCHAR UNIQUE,
                page_count INTEGER,
                received_at TIMESTAMP,
                status VARCHAR
            );

            CREATE TABLE IF NOT EXISTS document_profiles (
                document_id VARCHAR PRIMARY KEY REFERENCES documents(document_id),
                pdf_profile VARCHAR,
                has_text_layer BOOLEAN,
                text_character_count INTEGER,
                text_density DOUBLE,
                image_count INTEGER,
                full_page_image_ratio DOUBLE,
                requires_ocr BOOLEAN
            );

            CREATE TABLE IF NOT EXISTS processing_runs (
                run_id VARCHAR PRIMARY KEY,
                started_at TIMESTAMP,
                completed_at TIMESTAMP,
                total_documents INTEGER,
                processed_count INTEGER,
                accepted_count INTEGER DEFAULT 0,
                review_required_count INTEGER DEFAULT 0,
                failed_count INTEGER DEFAULT 0,
                status VARCHAR
            );

            CREATE TABLE IF NOT EXISTS parser_attempts (
                attempt_id VARCHAR PRIMARY KEY,
                document_id VARCHAR REFERENCES documents(document_id),
                run_id VARCHAR,
                requested_parser VARCHAR,
                actual_parser VARCHAR,
                attempt_number INTEGER,
                fallback_type VARCHAR,
                success BOOLEAN,
                started_at TIMESTAMP,
                completed_at TIMESTAMP,
                execution_time_seconds DOUBLE,
                error_type VARCHAR,
                error_message VARCHAR,
                quality_report_json VARCHAR,
                selected BOOLEAN DEFAULT TRUE
            );

            CREATE TABLE IF NOT EXISTS document_ir (
                document_id VARCHAR PRIMARY KEY REFERENCES documents(document_id),
                full_text VARCHAR,
                raw_json VARCHAR
            );

            CREATE TABLE IF NOT EXISTS business_documents (
                document_id VARCHAR PRIMARY KEY REFERENCES documents(document_id),
                document_family VARCHAR,
                source_format VARCHAR,
                document_number VARCHAR,
                issue_date VARCHAR,
                currency VARCHAR,
                grand_total DOUBLE,
                canonical_payload_json VARCHAR,
                field_candidates_json VARCHAR,
                completeness_score DOUBLE,
                created_at TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS canonical_versions (
                version_id VARCHAR PRIMARY KEY,
                document_id VARCHAR REFERENCES documents(document_id),
                version_number INTEGER,
                source VARCHAR,
                canonical_payload_json VARCHAR,
                created_at TIMESTAMP,
                reviewer VARCHAR,
                parent_version_id VARCHAR
            );

            CREATE TABLE IF NOT EXISTS parties (
                party_id VARCHAR PRIMARY KEY,
                document_id VARCHAR REFERENCES documents(document_id),
                role VARCHAR,
                name VARCHAR,
                tax_id VARCHAR,
                address VARCHAR,
                phone VARCHAR,
                email VARCHAR,
                bank_account VARCHAR
            );

            CREATE TABLE IF NOT EXISTS line_items (
                line_item_id VARCHAR PRIMARY KEY,
                document_id VARCHAR REFERENCES documents(document_id),
                description VARCHAR,
                quantity DOUBLE,
                unit VARCHAR,
                unit_price DOUBLE,
                amount DOUBLE
            );

            CREATE TABLE IF NOT EXISTS meter_readings (
                reading_id VARCHAR PRIMARY KEY,
                document_id VARCHAR REFERENCES documents(document_id),
                meter_number VARCHAR,
                opening_reading DOUBLE,
                closing_reading DOUBLE,
                consumption DOUBLE
            );

            CREATE TABLE IF NOT EXISTS container_records (
                container_id VARCHAR PRIMARY KEY,
                document_id VARCHAR REFERENCES documents(document_id),
                container_number VARCHAR,
                container_size VARCHAR,
                teu DOUBLE,
                amount DOUBLE
            );

            CREATE TABLE IF NOT EXISTS tax_certificates (
                certificate_id VARCHAR PRIMARY KEY,
                document_id VARCHAR REFERENCES documents(document_id),
                certificate_number VARCHAR,
                taxable_income DOUBLE,
                withheld_tax DOUBLE
            );

            CREATE TABLE IF NOT EXISTS validation_issues (
                issue_id VARCHAR PRIMARY KEY,
                document_id VARCHAR REFERENCES documents(document_id),
                code VARCHAR,
                severity VARCHAR,
                field_path VARCHAR,
                message VARCHAR,
                review_required BOOLEAN
            );

            CREATE TABLE IF NOT EXISTS review_queue (
                review_id VARCHAR PRIMARY KEY,
                document_id VARCHAR REFERENCES documents(document_id),
                reason VARCHAR,
                status VARCHAR,
                created_at TIMESTAMP,
                updated_at TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS review_corrections (
                correction_id VARCHAR PRIMARY KEY,
                document_id VARCHAR REFERENCES documents(document_id),
                canonical_version_before VARCHAR,
                canonical_version_after VARCHAR,
                field_path VARCHAR,
                old_value VARCHAR,
                new_value VARCHAR,
                reviewer VARCHAR,
                reason VARCHAR,
                created_at TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS exports (
                export_id VARCHAR PRIMARY KEY,
                run_id VARCHAR,
                export_path VARCHAR,
                export_type VARCHAR,
                created_at TIMESTAMP
            );
            """)

            # Add missing columns safely if migrating existing database
            for col_sql in [
                "ALTER TABLE parser_attempts ADD COLUMN IF NOT EXISTS fallback_type VARCHAR;",
                "ALTER TABLE parser_attempts ADD COLUMN IF NOT EXISTS started_at TIMESTAMP;",
                "ALTER TABLE parser_attempts ADD COLUMN IF NOT EXISTS completed_at TIMESTAMP;",
                "ALTER TABLE parser_attempts ADD COLUMN IF NOT EXISTS error_type VARCHAR;",
                "ALTER TABLE parser_attempts ADD COLUMN IF NOT EXISTS selected BOOLEAN DEFAULT TRUE;",
                "ALTER TABLE processing_runs ADD COLUMN IF NOT EXISTS accepted_count INTEGER DEFAULT 0;",
                "ALTER TABLE processing_runs ADD COLUMN IF NOT EXISTS review_required_count INTEGER DEFAULT 0;",
                "ALTER TABLE processing_runs ADD COLUMN IF NOT EXISTS failed_count INTEGER DEFAULT 0;",
                "ALTER TABLE review_corrections ADD COLUMN IF NOT EXISTS canonical_version_before VARCHAR;",
                "ALTER TABLE review_corrections ADD COLUMN IF NOT EXISTS canonical_version_after VARCHAR;",
                "ALTER TABLE review_corrections ADD COLUMN IF NOT EXISTS reason VARCHAR;",
            ]:
                try:
                    conn.execute(col_sql)
                except Exception:
                    pass

    def start_processing_run(self, run_id: str, total_documents: int) -> None:
        """Register a new processing batch run."""
        with self.get_connection() as conn:
            conn.execute(
                """
                INSERT INTO processing_runs (run_id, started_at, total_documents, processed_count, accepted_count, review_required_count, failed_count, status)
                VALUES (?, CURRENT_TIMESTAMP, ?, 0, 0, 0, 0, 'running')
                ON CONFLICT(run_id) DO UPDATE SET total_documents=excluded.total_documents, status='running';
                """,
                [run_id, total_documents],
            )

    def update_processing_run(
        self,
        run_id: str,
        processed_count: int,
        accepted_count: int,
        review_required_count: int,
        failed_count: int,
        status: str = "completed",
    ) -> None:
        """Update batch processing run state."""
        with self.get_connection() as conn:
            conn.execute(
                """
                UPDATE processing_runs
                SET processed_count = ?,
                    accepted_count = ?,
                    review_required_count = ?,
                    failed_count = ?,
                    completed_at = CURRENT_TIMESTAMP,
                    status = ?
                WHERE run_id = ?;
                """,
                [processed_count, accepted_count, review_required_count, failed_count, status, run_id],
            )

    def store_document(
        self,
        envelope: BusinessDocumentEnvelope,
        validation: ValidationResult,
        routing_decision: Optional[RoutingDecision] = None,
        routing_outcome: Optional[ParserRoutingOutcome] = None,
        completeness: Optional[FamilyCompletenessReport] = None,
        source_doc: Optional[SourceDocument] = None,
        run_id: str = "default_run",
    ) -> None:
        """Store document results inside an isolated transaction."""
        doc_id = envelope.document_id
        comp_score = completeness.completeness_score if completeness else 1.0

        # Source Document Metadata
        filename = source_doc.filename if source_doc else f"{doc_id}.pdf"
        rel_path = source_doc.path if source_doc else f"workspace/inbox/{filename}"
        sha256 = source_doc.sha256 if source_doc else None
        page_count = source_doc.page_count if source_doc else 1

        val_status = "accepted" if validation.is_valid and not (validation.requires_review or (completeness and completeness.requires_review)) else "review_required"

        with self.get_connection() as conn:
            conn.execute("BEGIN TRANSACTION;")
            try:
                # 1. Upsert documents
                conn.execute(
                    """
                    INSERT INTO documents (document_id, filename, path, mime_type, sha256, page_count, received_at, status)
                    VALUES (?, ?, ?, 'application/pdf', ?, ?, CURRENT_TIMESTAMP, ?)
                    ON CONFLICT(document_id) DO UPDATE SET status=excluded.status, page_count=excluded.page_count;
                    """,
                    [doc_id, filename, str(rel_path), sha256, page_count, val_status],
                )

                # 2. Relational Projector
                self.projector.project_and_store(conn, envelope, comp_score)

                # 3. Insert Initial Canonical Version (v1, machine_extracted)
                payload_json = envelope.payload.model_dump_json()
                v1_id = f"ver_{doc_id}_1"
                conn.execute(
                    """
                    INSERT INTO canonical_versions (version_id, document_id, version_number, source, canonical_payload_json, created_at, reviewer, parent_version_id)
                    VALUES (?, ?, 1, 'machine_extracted', ?, CURRENT_TIMESTAMP, 'system_pipeline', NULL)
                    ON CONFLICT(version_id) DO NOTHING;
                    """,
                    [v1_id, doc_id, payload_json],
                )

                # 4. Upsert Parser Attempts
                if routing_outcome:
                    # Log Primary Attempt
                    p_res = routing_outcome.primary_result
                    p_prov = p_res.document_ir.provenance if (p_res and p_res.document_ir) else None
                    p_exec_time = p_prov.execution_time_seconds if p_prov else (p_res.execution_time_seconds if hasattr(p_res, "execution_time_seconds") else 0.0)
                    p_actual = p_prov.parser_id if p_prov else routing_outcome.routing_decision.requested_parser
                    p_selected = (routing_outcome.selected_result == p_res)
                    p_qual_json = routing_outcome.routing_decision.quality_report.model_dump_json() if (p_selected and routing_outcome.routing_decision.quality_report) else None

                    conn.execute(
                        """
                        INSERT INTO parser_attempts (attempt_id, document_id, run_id, requested_parser, actual_parser, attempt_number, fallback_type, success, execution_time_seconds, error_message, quality_report_json, selected)
                        VALUES (?, ?, ?, ?, ?, 1, NULL, ?, ?, ?, ?, ?)
                        ON CONFLICT(attempt_id) DO UPDATE SET success=excluded.success, selected=excluded.selected;
                        """,
                        [
                            f"att_{doc_id}_1",
                            doc_id,
                            run_id,
                            routing_outcome.routing_decision.requested_parser,
                            p_actual,
                            p_res.success,
                            float(p_exec_time),
                            p_res.error_message,
                            p_qual_json,
                            p_selected,
                        ],
                    )

                    # Log Fallback Attempt if executed
                    if routing_outcome.fallback_result:
                        fb_res = routing_outcome.fallback_result
                        fb_prov = fb_res.document_ir.provenance if (fb_res and fb_res.document_ir) else None
                        fb_exec_time = fb_prov.execution_time_seconds if fb_prov else (fb_res.execution_time_seconds if hasattr(fb_res, "execution_time_seconds") else 0.0)
                        fb_actual = fb_prov.parser_id if fb_prov else "paddleocr_vl"
                        fb_selected = (routing_outcome.selected_result == fb_res)
                        fb_qual_json = routing_outcome.routing_decision.quality_report.model_dump_json() if (fb_selected and routing_outcome.routing_decision.quality_report) else None

                        conn.execute(
                            """
                            INSERT INTO parser_attempts (attempt_id, document_id, run_id, requested_parser, actual_parser, attempt_number, fallback_type, success, execution_time_seconds, error_message, quality_report_json, selected)
                            VALUES (?, ?, ?, ?, ?, 2, 'semantic_fallback', ?, ?, ?, ?, ?)
                            ON CONFLICT(attempt_id) DO UPDATE SET success=excluded.success, selected=excluded.selected;
                            """,
                            [
                                f"att_{doc_id}_2",
                                doc_id,
                                run_id,
                                "paddleocr_vl",
                                fb_actual,
                                fb_res.success,
                                float(fb_exec_time),
                                fb_res.error_message,
                                fb_qual_json,
                                fb_selected,
                            ],
                        )
                elif routing_decision:
                    qual_json = (
                        routing_decision.quality_report.model_dump_json()
                        if routing_decision.quality_report
                        else None
                    )
                    conn.execute(
                        """
                        INSERT INTO parser_attempts (attempt_id, document_id, run_id, requested_parser, actual_parser, attempt_number, success, execution_time_seconds, error_message, quality_report_json, selected)
                        VALUES (?, ?, ?, ?, ?, ?, NULL, TRUE, 0.0, NULL, ?, TRUE)
                        ON CONFLICT(attempt_id) DO UPDATE SET actual_parser=excluded.actual_parser;
                        """,
                        [
                            f"att_{doc_id}_{routing_decision.attempt_number}",
                            doc_id,
                            run_id,
                            routing_decision.requested_parser,
                            routing_decision.actual_parser,
                            routing_decision.attempt_number,
                            qual_json,
                        ],
                    )

                # 5. Store validation issues
                for idx, issue in enumerate(validation.issues):
                    conn.execute(
                        """
                        INSERT INTO validation_issues (issue_id, document_id, code, severity, field_path, message, review_required)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(issue_id) DO NOTHING;
                        """,
                        [
                            f"{doc_id}_v{idx}",
                            doc_id,
                            issue.code,
                            issue.severity.value,
                            issue.field_path,
                            issue.message,
                            issue.review_required,
                        ],
                    )

                # 6. Store in review queue if review required
                if val_status == "review_required":
                    reason_msg = validation.issues[0].code if validation.issues else "completeness_review_required"
                    conn.execute(
                        """
                        INSERT INTO review_queue (review_id, document_id, reason, status, created_at, updated_at)
                        VALUES (?, ?, ?, 'pending', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                        ON CONFLICT(review_id) DO NOTHING;
                        """,
                        [f"rev_{doc_id}", doc_id, reason_msg],
                    )

                conn.execute("COMMIT;")
            except Exception:
                conn.execute("ROLLBACK;")
                raise
