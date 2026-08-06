"""Unit tests for DuckDBAggregator."""

from decimal import Decimal
from document_benchmark.aggregation.duckdb_engine import DuckDBAggregator


def test_duckdb_financial_aggregation():
    agg = DuckDBAggregator()
    documents = [
        {"document_id": "doc1", "filename": "inv1.pdf", "page_count": 1, "document_family": "invoice"}
    ]
    canonical_results = [
        {
            "run_id": "run1",
            "document_id": "doc1",
            "source_config": "mock_default",
            "canonical_payload": {
                "invoice_number": "0001234",
                "seller_name": "Logistics Ltd",
                "subtotal": Decimal("10000000.00"),
                "vat_amount": Decimal("1000000.00"),
                "total_amount": Decimal("11000000.00"),
            },
        }
    ]
    metrics = [
        {
            "run_id": "run1",
            "document_id": "doc1",
            "config_id": "mock_default",
            "run_index": 1,
            "is_warmup": False,
            "status": "SUCCESS",
            "success": True,
            "total_pipeline_ms": 150.0,
            "resource_summary": {"rss_peak_mb": 45.0},
        }
    ]

    agg.load_run_data(documents, canonical_results, [], metrics)

    totals = agg.query_engine_financial_totals()
    assert len(totals) == 1
    assert totals[0]["config_id"] == "mock_default"
    assert totals[0]["total_amount"] == 11000000.0

    lat = agg.query_engine_latency_leaderboard()
    assert len(lat) == 1
    assert lat[0]["mean_latency_ms"] == 150.0

    agg.close()
