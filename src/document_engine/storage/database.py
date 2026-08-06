"""DuckDB storage engine with idempotent schema migrations and isolated document transactions."""

import json
from pathlib import Path
import duckdb

from document_engine.schemas.family_schemas import BusinessDocumentEnvelope
from document_engine.validation.validator import ValidationResult


class DuckDBStorage:
    def __init__(self, db_path: Path):
        self.db_path = Path(db_path).resolve()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
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
                status VARCHAR
            );

            CREATE TABLE IF NOT EXISTS parser_attempts (
                attempt_id VARCHAR PRIMARY KEY,
                document_id VARCHAR REFERENCES documents(document_id),
                run_id VARCHAR,
                parser_id VARCHAR,
                attempt_number INTEGER,
                success BOOLEAN,
                execution_time_seconds DOUBLE,
                error_message VARCHAR
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
                created_at TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS parties (
                party_id VARCHAR PRIMARY KEY,
                document_id VARCHAR REFERENCES documents(document_id),
                role VARCHAR, -- seller, buyer, payer, payee, organization, recipient
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
                field_path VARCHAR,
                old_value VARCHAR,
                new_value VARCHAR,
                reviewer VARCHAR,
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

    def store_document(
        self,
        envelope: BusinessDocumentEnvelope,
        validation: ValidationResult,
        run_id: str = "default_run",
    ) -> None:
        """Store document results inside an isolated transaction."""
        doc_id = envelope.document_id
        payload_dict = envelope.payload.model_dump(mode="json")
        payload_json = json.dumps(payload_dict, ensure_ascii=False)

        with self.get_connection() as conn:
            conn.execute("BEGIN TRANSACTION;")
            try:
                # Upsert documents
                conn.execute(
                    """
                    INSERT INTO documents (document_id, filename, path, mime_type, sha256, page_count, received_at, status)
                    VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, ?)
                    ON CONFLICT(document_id) DO UPDATE SET status=excluded.status;
                    """,
                    [
                        doc_id,
                        f"{doc_id}.pdf",
                        f"/workspace/inbox/{doc_id}.pdf",
                        "application/pdf",
                        doc_id.replace("doc_", ""),
                        1,
                        "validated" if validation.is_valid else "review_required",
                    ],
                )

                # Upsert business_documents
                common = getattr(envelope.payload, "common", None)
                doc_num = common.document_number if common else None
                issue_date = common.issue_date if common else None
                grand_total = float(common.grand_total) if (common and common.grand_total is not None) else 0.0

                conn.execute(
                    """
                    INSERT INTO business_documents (document_id, document_family, source_format, document_number, issue_date, currency, grand_total, canonical_payload_json, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                    ON CONFLICT(document_id) DO UPDATE SET
                        document_number=excluded.document_number,
                        grand_total=excluded.grand_total,
                        canonical_payload_json=excluded.canonical_payload_json;
                    """,
                    [
                        doc_id,
                        envelope.document_family.value,
                        envelope.source_format.value,
                        doc_num,
                        issue_date,
                        "VND",
                        grand_total,
                        payload_json,
                    ],
                )

                # Store validation issues
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

                # Store in review queue if review required
                if validation.requires_review:
                    conn.execute(
                        """
                        INSERT INTO review_queue (review_id, document_id, reason, status, created_at, updated_at)
                        VALUES (?, ?, ?, 'pending', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                        ON CONFLICT(review_id) DO NOTHING;
                        """,
                        [
                            f"rev_{doc_id}",
                            doc_id,
                            validation.issues[0].code if validation.issues else "review_required",
                        ],
                    )

                conn.execute("COMMIT;")
            except Exception as e:
                conn.execute("ROLLBACK;")
                raise e
