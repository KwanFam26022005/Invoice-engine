"""Tests for versioned engine configuration truthfulness."""

from pathlib import Path

import yaml


CONFIG_DIR = Path("configs/engines")


def load_config(name: str) -> dict:
    return yaml.safe_load((CONFIG_DIR / name).read_text(encoding="utf-8"))


def test_ppstructure_v3_config_uses_v3_identity() -> None:
    config = load_config("ppstructure_v3.yaml")
    assert config["engine_id"] == "ppstructure_v3"
    assert config["config_id"] == "ppstructure_v3_vi_table_cpu"
    assert str(config["engine_version"]).startswith("3")
    assert config["options"]["benchmark_track"] == "scan_ocr"
    assert config["options"]["use_formula_recognition"] is False


def test_ppstructure_v2_config_is_disabled_and_explicit() -> None:
    config = load_config("ppstructure_v2_legacy.yaml")
    assert config["engine_id"] == "ppstructure_v2_legacy"
    assert "legacy" in config["config_id"]
    assert str(config["engine_version"]).startswith("2")
    assert config["enabled"] is False


def test_docling_profiles_are_separated_by_track() -> None:
    text_config = load_config("docling_text_only.yaml")
    table_config = load_config("docling_table.yaml")
    ocr_config = load_config("docling_ocr.yaml")

    assert text_config["options"]["benchmark_track"] == "native_pdf"
    assert table_config["options"]["benchmark_track"] == "native_pdf"
    assert text_config["supports_scanned_pdf"] is False
    assert table_config["supports_scanned_pdf"] is False

    assert ocr_config["options"]["benchmark_track"] == "scan_ocr"
    assert ocr_config["supports_scanned_pdf"] is True
    assert ocr_config["options"]["do_ocr"] is True
    assert ocr_config["options"]["ocr_languages"] == ["vi", "en"]
