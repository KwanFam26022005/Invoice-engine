"""Unit tests for Excel Exporter formula injection protection."""

from pathlib import Path
from document_engine.export.exporter import ExcelExporter
from document_engine.storage.database import DuckDBStorage


def test_sanitize_cell_value_formula_injection(tmp_path: Path):
    db_path = tmp_path / "dummy.duckdb"
    storage = DuckDBStorage(db_path)
    exporter = ExcelExporter(storage)

    assert exporter.sanitize_cell_value("=1+2") == "'=1+2"
    assert exporter.sanitize_cell_value("+100") == "'+100"
    assert exporter.sanitize_cell_value("-50") == "'-50"
    assert exporter.sanitize_cell_value("@SUM(A1)") == "'@SUM(A1)"
    assert exporter.sanitize_cell_value("Normal Text") == "Normal Text"
    assert exporter.sanitize_cell_value(123) == 123
