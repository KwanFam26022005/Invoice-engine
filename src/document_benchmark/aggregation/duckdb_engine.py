"""DuckDB In-Memory aggregation engine for benchmark analytics."""

from typing import Any, Dict, List
import duckdb


class DuckDBAggregator:
    """In-memory analytics aggregator using DuckDB."""

    def __init__(self) -> None:
        self.conn = duckdb.connect(database=":memory:")
        self._init_tables()

    def _init_tables(self) -> None:
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS documents (
                document_id VARCHAR,
                filename VARCHAR,
                sha256 VARCHAR,
                page_count INTEGER,
                document_family VARCHAR,
                document_subtype VARCHAR
            );
            """
        )

        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS invoices (
                run_id VARCHAR,
                document_id VARCHAR,
                config_id VARCHAR,
                invoice_number VARCHAR,
                invoice_series VARCHAR,
                invoice_date VARCHAR,
                seller_name VARCHAR,
                seller_tax_id VARCHAR,
                buyer_name VARCHAR,
                buyer_tax_id VARCHAR,
                subtotal DECIMAL(18, 2),
                discount_amount DECIMAL(18, 2),
                vat_amount DECIMAL(18, 2),
                total_amount DECIMAL(18, 2),
                requires_review BOOLEAN
            );
            """
        )

        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS invoice_items (
                run_id VARCHAR,
                document_id VARCHAR,
                config_id VARCHAR,
                line_number INTEGER,
                description VARCHAR,
                unit VARCHAR,
                quantity DECIMAL(18, 4),
                unit_price DECIMAL(18, 2),
                amount DECIMAL(18, 2)
            );
            """
        )

        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS validation_issues (
                run_id VARCHAR,
                document_id VARCHAR,
                config_id VARCHAR,
                code VARCHAR,
                severity VARCHAR,
                field_path VARCHAR,
                message VARCHAR
            );
            """
        )

        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS engine_metrics (
                run_id VARCHAR,
                document_id VARCHAR,
                config_id VARCHAR,
                run_index INTEGER,
                is_warmup BOOLEAN,
                status VARCHAR,
                success BOOLEAN,
                prepare_time_ms DOUBLE,
                extract_time_ms DOUBLE,
                total_pipeline_ms DOUBLE,
                cpu_peak_percent DOUBLE,
                rss_peak_mb DOUBLE,
                vms_peak_mb DOUBLE,
                read_bytes BIGINT,
                write_bytes BIGINT
            );
            """
        )

    def load_run_data(
        self,
        documents: List[Dict[str, Any]],
        canonical_results: List[Dict[str, Any]],
        validation_issues: List[Dict[str, Any]],
        metrics_results: List[Dict[str, Any]],
    ) -> None:
        """Populate DuckDB in-memory tables."""
        # Insert documents
        for doc in documents:
            self.conn.execute(
                """
                INSERT INTO documents VALUES (?, ?, ?, ?, ?, ?);
                """,
                [
                    doc.get("document_id"),
                    doc.get("filename"),
                    doc.get("sha256"),
                    doc.get("page_count", 1),
                    doc.get("document_family", "unknown"),
                    doc.get("document_subtype", "unknown"),
                ],
            )

        # Insert invoices & items
        for can in canonical_results:
            p = can.get("canonical_payload", {})
            self.conn.execute(
                """
                INSERT INTO invoices VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                [
                    can.get("run_id", ""),
                    can.get("document_id", ""),
                    can.get("source_config", ""),
                    p.get("invoice_number"),
                    p.get("invoice_series"),
                    p.get("invoice_date"),
                    p.get("seller_name"),
                    p.get("seller_tax_id"),
                    p.get("buyer_name"),
                    p.get("buyer_tax_id"),
                    p.get("subtotal"),
                    p.get("discount_amount"),
                    p.get("vat_amount"),
                    p.get("total_amount"),
                    can.get("requires_review", False),
                ],
            )

            for item in p.get("line_items", []):
                self.conn.execute(
                    """
                    INSERT INTO invoice_items VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
                    """,
                    [
                        can.get("run_id", ""),
                        can.get("document_id", ""),
                        can.get("source_config", ""),
                        item.get("line_number"),
                        item.get("description"),
                        item.get("unit"),
                        item.get("quantity"),
                        item.get("unit_price"),
                        item.get("amount_after_tax"),
                    ],
                )

        # Insert validation issues
        for issue in validation_issues:
            self.conn.execute(
                """
                INSERT INTO validation_issues VALUES (?, ?, ?, ?, ?, ?, ?);
                """,
                [
                    issue.get("run_id", ""),
                    issue.get("document_id", ""),
                    issue.get("source_engine", ""),
                    issue.get("code", ""),
                    issue.get("severity", ""),
                    issue.get("field_path", ""),
                    issue.get("message", ""),
                ],
            )

        # Insert engine metrics
        for m in metrics_results:
            rs = m.get("resource_summary", {})
            self.conn.execute(
                """
                INSERT INTO engine_metrics VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                [
                    m.get("run_id", ""),
                    m.get("document_id", ""),
                    m.get("config_id", ""),
                    m.get("run_index", 1),
                    m.get("is_warmup", False),
                    m.get("status", "SUCCESS"),
                    m.get("success", True),
                    m.get("prepare_time_ms", 0.0),
                    m.get("extract_time_ms", 0.0),
                    m.get("total_pipeline_ms", 0.0),
                    rs.get("cpu_peak_percent", 0.0),
                    rs.get("rss_peak_mb", 0.0),
                    rs.get("vms_peak_mb", 0.0),
                    rs.get("read_bytes_total", 0),
                    rs.get("write_bytes_total", 0),
                ],
            )

    def query_engine_financial_totals(self) -> List[Dict[str, Any]]:
        """Aggregate total financial amounts by engine config."""
        res = self.conn.execute(
            """
            SELECT 
                config_id,
                COUNT(DISTINCT document_id) as doc_count,
                SUM(subtotal) as total_subtotal,
                SUM(vat_amount) as total_vat,
                SUM(total_amount) as total_amount
            FROM invoices
            GROUP BY config_id;
            """
        ).fetchall()

        cols = ["config_id", "doc_count", "total_subtotal", "total_vat", "total_amount"]
        return [dict(zip(cols, row)) for row in res]

    def query_engine_latency_leaderboard(self) -> List[Dict[str, Any]]:
        """Aggregate latency metrics (mean, p50, p95, min, max, peak RAM) by engine."""
        res = self.conn.execute(
            """
            SELECT 
                config_id,
                COUNT(*) as run_count,
                SUM(CASE WHEN success = true THEN 1 ELSE 0 END) as success_count,
                AVG(total_pipeline_ms) as mean_latency_ms,
                QUANTILE_CONT(total_pipeline_ms, 0.50) as p50_latency_ms,
                QUANTILE_CONT(total_pipeline_ms, 0.95) as p95_latency_ms,
                MIN(total_pipeline_ms) as min_latency_ms,
                MAX(total_pipeline_ms) as max_latency_ms,
                MAX(rss_peak_mb) as peak_ram_mb
            FROM engine_metrics
            WHERE is_warmup = false
            GROUP BY config_id;
            """
        ).fetchall()

        cols = [
            "config_id",
            "run_count",
            "success_count",
            "mean_latency_ms",
            "p50_latency_ms",
            "p95_latency_ms",
            "min_latency_ms",
            "max_latency_ms",
            "peak_ram_mb",
        ]
        return [dict(zip(cols, row)) for row in res]

    def close(self) -> None:
        self.conn.close()
