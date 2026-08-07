"""Unit tests for parser config loading, precedence, and end-to-end plumbing."""

import pytest

from document_engine.config.parser_config import (
    apply_env_overrides,
    load_parser_config,
    merge_parser_config,
)


def test_load_parser_config_from_yaml(tmp_path):
    """Load a valid YAML config file and extract the config sub-key."""
    config_dir = tmp_path / "parsers"
    config_dir.mkdir()
    (config_dir / "test_parser.yaml").write_text(
        "parser_id: test_parser\nconfig:\n  key1: value1\n  key2: 42\n",
        encoding="utf-8",
    )

    result = load_parser_config("test_parser", config_dir=config_dir)
    assert result == {"key1": "value1", "key2": 42}


def test_load_parser_config_missing_file(tmp_path):
    """Missing config file returns empty dict (defaults apply)."""
    result = load_parser_config("nonexistent", config_dir=tmp_path)
    assert result == {}


def test_load_parser_config_parser_id_mismatch(tmp_path):
    """YAML parser_id mismatch raises ValueError."""
    config_dir = tmp_path / "parsers"
    config_dir.mkdir()
    (config_dir / "wrong_parser.yaml").write_text(
        "parser_id: actual_parser\nconfig:\n  key: val\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="identity mismatch"):
        load_parser_config("wrong_parser", config_dir=config_dir)


def test_load_parser_config_no_parser_id_in_yaml(tmp_path):
    """YAML without parser_id field loads without error."""
    config_dir = tmp_path / "parsers"
    config_dir.mkdir()
    (config_dir / "simple.yaml").write_text(
        "config:\n  x: 1\n",
        encoding="utf-8",
    )

    result = load_parser_config("simple", config_dir=config_dir)
    assert result == {"x": 1}


def test_load_parser_config_env_override_dir(tmp_path, monkeypatch):
    """DOCUMENT_ENGINE_PARSER_CONFIG_DIR env var overrides default config dir."""
    config_dir = tmp_path / "custom_configs"
    config_dir.mkdir()
    (config_dir / "env_test.yaml").write_text(
        "parser_id: env_test\nconfig:\n  custom: true\n",
        encoding="utf-8",
    )

    monkeypatch.setenv("DOCUMENT_ENGINE_PARSER_CONFIG_DIR", str(config_dir))
    result = load_parser_config("env_test")
    assert result == {"custom": True}


def test_load_parser_config_yaml_safe_load(tmp_path):
    """Verify yaml.safe_load is used (no arbitrary object deserialization)."""
    config_dir = tmp_path / "parsers"
    config_dir.mkdir()
    # YAML with Python-specific tag should not deserialize to Python object
    (config_dir / "unsafe_test.yaml").write_text(
        "parser_id: unsafe_test\nconfig:\n  value: !!python/object/apply:os.getcwd []\n",
        encoding="utf-8",
    )

    import yaml

    with pytest.raises(yaml.constructor.ConstructorError):
        load_parser_config("unsafe_test", config_dir=config_dir)


def test_apply_env_overrides_paddle(monkeypatch):
    """Paddle env overrides set model directory keys."""
    monkeypatch.setenv("PADDLE_LAYOUT_MODEL_DIR", "/models/layout")
    monkeypatch.setenv("PADDLE_VL_REC_MODEL_DIR", "/models/vl-rec")

    config = {"device": "cpu"}
    result = apply_env_overrides("paddleocr_vl", config)

    assert result["layout_detection_model_dir"] == "/models/layout"
    assert result["vl_rec_model_dir"] == "/models/vl-rec"
    assert result["device"] == "cpu"
    # Original config not mutated
    assert "layout_detection_model_dir" not in config


def test_apply_env_overrides_non_paddle():
    """Non-paddle parsers get config returned unchanged."""
    config = {"do_ocr": True}
    result = apply_env_overrides("docling_ocr", config)
    assert result == config


def test_merge_parser_config_precedence():
    """Precedence: defaults < loaded YAML < env overrides."""
    defaults = {"a": 1, "b": 2, "c": 3}
    loaded = {"b": 20, "d": 40}
    env = {"c": 300}

    merged = merge_parser_config(defaults, loaded, env)
    assert merged == {"a": 1, "b": 20, "c": 300, "d": 40}


def test_merge_parser_config_null_yaml_skipped():
    """YAML null values do not override defaults."""
    defaults = {"pipeline_version": "v1.6", "device": "cpu"}
    loaded = {"pipeline_version": None, "device": "gpu"}
    env = {}

    merged = merge_parser_config(defaults, loaded, env)
    assert merged["pipeline_version"] == "v1.6"  # null skipped
    assert merged["device"] == "gpu"  # explicit override


def test_end_to_end_config_plumbing(tmp_path, monkeypatch):
    """Full config pipeline: YAML + env -> ParserRegistry -> parser.spec.config."""
    # Setup YAML config
    config_dir = tmp_path / "parsers"
    config_dir.mkdir()
    (config_dir / "paddleocr_vl.yaml").write_text(
        (
            "parser_id: paddleocr_vl\n"
            "config:\n"
            "  pipeline_version: v1.6\n"
            "  device: cpu\n"
            "  engine: paddle\n"
        ),
        encoding="utf-8",
    )

    # Setup fake model dirs
    layout_dir = tmp_path / "models" / "layout"
    vl_rec_dir = tmp_path / "models" / "vl-rec"
    layout_dir.mkdir(parents=True)
    vl_rec_dir.mkdir(parents=True)
    (layout_dir / "model.pdiparams").write_text("weight", encoding="utf-8")
    (vl_rec_dir / "model.safetensors").write_text("weight", encoding="utf-8")

    # Set env overrides
    monkeypatch.setenv("PADDLE_LAYOUT_MODEL_DIR", str(layout_dir))
    monkeypatch.setenv("PADDLE_VL_REC_MODEL_DIR", str(vl_rec_dir))

    from document_engine.parsers.registry import ParserRegistry

    registry = ParserRegistry()
    parser = registry.get_parser("paddleocr_vl", config_dir=config_dir)

    # Verify config plumbing
    assert parser.spec.config["layout_detection_model_dir"] == str(layout_dir)
    assert parser.spec.config["vl_rec_model_dir"] == str(vl_rec_dir)
    assert parser.spec.config["pipeline_version"] == "v1.6"
    assert parser.spec.config["device"] == "cpu"


def test_end_to_end_env_overrides_yaml(tmp_path, monkeypatch):
    """Env vars override YAML values."""
    config_dir = tmp_path / "parsers"
    config_dir.mkdir()
    (config_dir / "paddleocr_vl.yaml").write_text(
        (
            "parser_id: paddleocr_vl\n"
            "config:\n"
            "  layout_detection_model_dir: /yaml/layout\n"
            "  vl_rec_model_dir: /yaml/vl\n"
        ),
        encoding="utf-8",
    )

    monkeypatch.setenv("PADDLE_LAYOUT_MODEL_DIR", "/env/layout")
    monkeypatch.setenv("PADDLE_VL_REC_MODEL_DIR", "/env/vl")

    from document_engine.parsers.registry import ParserRegistry

    registry = ParserRegistry()
    parser = registry.get_parser("paddleocr_vl", config_dir=config_dir)

    # Env wins over YAML
    assert parser.spec.config["layout_detection_model_dir"] == "/env/layout"
    assert parser.spec.config["vl_rec_model_dir"] == "/env/vl"


def test_registry_missing_config_uses_defaults(tmp_path, monkeypatch):
    """Registry with empty config dir uses built-in defaults."""
    # Point to empty dir with no YAML files
    monkeypatch.delenv("PADDLE_LAYOUT_MODEL_DIR", raising=False)
    monkeypatch.delenv("PADDLE_VL_REC_MODEL_DIR", raising=False)

    from document_engine.parsers.registry import ParserRegistry

    registry = ParserRegistry()
    parser = registry.get_parser("paddleocr_vl", config_dir=tmp_path)

    # Built-in defaults should be present
    assert parser.spec.config["pipeline_version"] == "v1.6"
    assert parser.spec.config["device"] == "cpu"
    assert parser.spec.config["use_layout_detection"] is True


def test_healthcheck_receives_merged_config(tmp_path, monkeypatch):
    """Healthcheck WorkerRequest receives the fully merged config with model dirs."""
    from unittest.mock import MagicMock

    layout_dir = tmp_path / "models" / "layout"
    vl_rec_dir = tmp_path / "models" / "vl-rec"
    layout_dir.mkdir(parents=True)
    vl_rec_dir.mkdir(parents=True)

    monkeypatch.setenv("PADDLE_LAYOUT_MODEL_DIR", str(layout_dir))
    monkeypatch.setenv("PADDLE_VL_REC_MODEL_DIR", str(vl_rec_dir))

    from document_engine.parsers.registry import ParserRegistry

    registry = ParserRegistry()
    parser = registry.get_parser("paddleocr_vl", config_dir=tmp_path)

    captured = []

    class MockWorkerClient:
        def execute_worker(self, request):
            captured.append(request)
            return MagicMock(
                success=True,
                health_data={"python_executable": "python.exe", "paddle_installed": True},
            )

    parser.worker_client = MockWorkerClient()
    parser.healthcheck()

    assert len(captured) == 1
    req = captured[0]
    assert req.operation == "healthcheck"
    assert req.options["layout_detection_model_dir"] == str(layout_dir)
    assert req.options["vl_rec_model_dir"] == str(vl_rec_dir)


def test_registry_constructor_type_error_propagates():
    """Verify that constructor TypeError propagates from registry instead of being swallowed."""
    from document_engine.parsers.base import DocumentParser, ParserHealth, ParserSpec
    from document_engine.parsers.registry import ParserRegistry

    class IncompatibleParser(DocumentParser):
        def __init__(self, positional_only_arg):
            # Does not accept config keyword argument
            self.arg = positional_only_arg

        @property
        def spec(self) -> ParserSpec:
            return ParserSpec(parser_id="incompatible", name="Incompatible")

        def healthcheck(self) -> ParserHealth:
            return ParserHealth(parser_id="incompatible", healthy=True)

        def supports(self, profile) -> bool:
            return True

        def parse(self, document, profile):
            pass

    registry = ParserRegistry()
    registry.register("incompatible", IncompatibleParser)

    with pytest.raises(TypeError):
        registry.get_parser("incompatible")

