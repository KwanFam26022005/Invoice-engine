"""Relational projector for expanding BusinessDocumentEnvelope into normalized database tables."""

import duckdb

from document_engine.schemas.family_schemas import BusinessDocumentEnvelope


class RelationalProjector:
    """Projects canonical BusinessDocumentEnvelope payloads into relational DuckDB tables."""

    def project_and_store(
        self,
        conn: duckdb.DuckDBPyConnection,
        envelope: BusinessDocumentEnvelope,
        completeness_score: float = 1.0,
    ) -> None:
        """Clear existing relational rows for document_id and insert projected records."""
        doc_id = envelope.document_id
        payload = envelope.payload
        payload_dict = payload.model_dump(mode="json")
        payload_json = envelope.payload.model_dump_json()

        candidates_dict = {
            k: v.model_dump(mode="json") for k, v in envelope.field_candidates.items()
        }
        import json
        candidates_json = json.dumps(candidates_dict, ensure_ascii=False)

        # 1. Clean existing relational child records for this document
        conn.execute("DELETE FROM parties WHERE document_id = ?;", [doc_id])
        conn.execute("DELETE FROM line_items WHERE document_id = ?;", [doc_id])
        conn.execute("DELETE FROM meter_readings WHERE document_id = ?;", [doc_id])
        conn.execute("DELETE FROM container_records WHERE document_id = ?;", [doc_id])
        conn.execute("DELETE FROM tax_certificates WHERE document_id = ?;", [doc_id])

        # 2. Upsert business_documents
        common = getattr(payload, "common", None)
        doc_num = common.document_number if common else None
        issue_date = common.issue_date if common else None
        currency = common.currency if (common and common.currency) else "VND"
        grand_total = common.grand_total if (common and common.grand_total is not None) else None

        conn.execute(
            """
            INSERT INTO business_documents (document_id, document_family, source_format, document_number, issue_date, currency, grand_total, canonical_payload_json, field_candidates_json, completeness_score, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(document_id) DO UPDATE SET
                document_family=excluded.document_family,
                source_format=excluded.source_format,
                document_number=excluded.document_number,
                issue_date=excluded.issue_date,
                currency=excluded.currency,
                grand_total=excluded.grand_total,
                canonical_payload_json=excluded.canonical_payload_json,
                field_candidates_json=excluded.field_candidates_json,
                completeness_score=excluded.completeness_score;
            """,
            [
                doc_id,
                envelope.document_family.value,
                envelope.source_format.value,
                doc_num,
                issue_date,
                currency,
                float(grand_total) if grand_total is not None else None,
                payload_json,
                candidates_json,
                completeness_score,
            ],
        )

        # 3. Project Parties (seller / buyer)
        if common:
            if common.seller:
                s = common.seller
                conn.execute(
                    """
                    INSERT INTO parties (party_id, document_id, role, name, tax_id, address, phone, email, bank_account)
                    VALUES (?, ?, 'seller', ?, ?, ?, ?, ?, ?);
                    """,
                    [
                        f"{doc_id}_party_seller",
                        doc_id,
                        s.name,
                        s.tax_id,
                        s.address,
                        s.phone,
                        s.email,
                        s.bank_account,
                    ],
                )
            if common.buyer:
                b = common.buyer
                conn.execute(
                    """
                    INSERT INTO parties (party_id, document_id, role, name, tax_id, address, phone, email, bank_account)
                    VALUES (?, ?, 'buyer', ?, ?, ?, ?, ?, ?);
                    """,
                    [
                        f"{doc_id}_party_buyer",
                        doc_id,
                        b.name,
                        b.tax_id,
                        b.address,
                        b.phone,
                        b.email,
                        b.bank_account,
                    ],
                )

        # 4. Project Line Items
        line_items = getattr(payload, "line_items", []) or []
        for idx, item in enumerate(line_items):
            conn.execute(
                """
                INSERT INTO line_items (line_item_id, document_id, description, quantity, unit, unit_price, amount)
                VALUES (?, ?, ?, ?, ?, ?, ?);
                """,
                [
                    f"{doc_id}_li_{idx:03d}",
                    doc_id,
                    item.description,
                    float(item.quantity) if item.quantity is not None else None,
                    item.unit,
                    float(item.unit_price) if item.unit_price is not None else None,
                    float(item.amount) if item.amount is not None else None,
                ],
            )

        # 5. Project Meter Readings
        meter_readings = getattr(payload, "meter_readings", []) or []
        for idx, m in enumerate(meter_readings):
            conn.execute(
                """
                INSERT INTO meter_readings (reading_id, document_id, meter_number, opening_reading, closing_reading, consumption)
                VALUES (?, ?, ?, ?, ?, ?);
                """,
                [
                    f"{doc_id}_mr_{idx:03d}",
                    doc_id,
                    m.meter_number,
                    float(m.opening_reading) if m.opening_reading is not None else None,
                    float(m.closing_reading) if m.closing_reading is not None else None,
                    float(m.consumption) if m.consumption is not None else None,
                ],
            )

        # 6. Project Container Records
        container_records = getattr(payload, "container_records", []) or []
        for idx, c in enumerate(container_records):
            conn.execute(
                """
                INSERT INTO container_records (container_id, document_id, container_number, container_size, teu, amount)
                VALUES (?, ?, ?, ?, ?, ?);
                """,
                [
                    f"{doc_id}_cr_{idx:03d}",
                    doc_id,
                    c.container_number,
                    c.container_size,
                    float(c.teu) if c.teu is not None else None,
                    float(c.amount) if c.amount is not None else None,
                ],
            )

        # 7. Project Tax Certificates
        if hasattr(payload, "certificate_number") or hasattr(payload, "withheld_tax"):
            cert_num = getattr(payload, "certificate_number", None)
            income = getattr(payload, "total_taxable_income", None)
            tax = getattr(payload, "withheld_tax", None)
            conn.execute(
                """
                INSERT INTO tax_certificates (certificate_id, document_id, certificate_number, taxable_income, withheld_tax)
                VALUES (?, ?, ?, ?, ?);
                """,
                [
                    f"{doc_id}_tc_001",
                    doc_id,
                    cert_num,
                    float(income) if income is not None else None,
                    float(tax) if tax is not None else None,
                ],
            )
