"""Parser configuration loader with YAML file support and environment overrides."""

import os
from pathlib import Path
from typing import Any, Dict, Optional

import yaml


_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
_DEFAULT_CONFIG_DIR = _REPO_ROOT / "configs" / "parsers"


def load_parser_config(
    parser_id: str,
    config_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    """Load parser configuration from YAML file.

    Args:
        parser_id: The parser identifier (e.g. 'paddleocr_vl').
        config_dir: Directory containing parser YAML files.
            Defaults to DOCUMENT_ENGINE_PARSER_CONFIG_DIR env var,
            or configs/parsers/ relative to repository root.

    Returns:
        The 'config' sub-key from the YAML file as a dict,
        or empty dict if file is missing.

    Raises:
        ValueError: If YAML parser_id doesn't match requested parser_id.
    """
    if config_dir is None:
        env_dir = os.getenv("DOCUMENT_ENGINE_PARSER_CONFIG_DIR")
        if env_dir:
            config_dir = Path(env_dir)
        else:
            config_dir = _DEFAULT_CONFIG_DIR

    config_path = config_dir / f"{parser_id}.yaml"
    if not config_path.is_file():
        return {}

    with open(config_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    if not isinstance(data, dict):
        return {}

    # Validate parser_id identity
    yaml_parser_id = data.get("parser_id")
    if yaml_parser_id is not None and yaml_parser_id != parser_id:
        raise ValueError(
            f"Parser config identity mismatch: requested '{parser_id}' "
            f"but YAML declares parser_id='{yaml_parser_id}'"
        )

    return dict(data.get("config", {}) or {})


def apply_env_overrides(parser_id: str, config: Dict[str, Any]) -> Dict[str, Any]:
    """Apply environment variable overrides to parser config.

    For paddleocr_vl:
        PADDLE_LAYOUT_MODEL_DIR -> layout_detection_model_dir
        PADDLE_VL_REC_MODEL_DIR -> vl_rec_model_dir

    Args:
        parser_id: The parser identifier.
        config: Base config dict (not mutated).

    Returns:
        New dict with environment overrides applied.
    """
    result = dict(config)

    if parser_id == "paddleocr_vl":
        layout_dir = os.getenv("PADDLE_LAYOUT_MODEL_DIR")
        if layout_dir:
            result["layout_detection_model_dir"] = layout_dir

        vl_rec_dir = os.getenv("PADDLE_VL_REC_MODEL_DIR")
        if vl_rec_dir:
            result["vl_rec_model_dir"] = vl_rec_dir

    return result


def merge_parser_config(
    defaults: Dict[str, Any],
    loaded: Dict[str, Any],
    env_overrides: Dict[str, Any],
) -> Dict[str, Any]:
    """Merge parser config with precedence: defaults < loaded YAML < env overrides.

    None values in loaded config are skipped (YAML null does not override defaults).
    None values in env_overrides are also skipped.

    Args:
        defaults: Built-in safe defaults from parser class.
        loaded: Config loaded from YAML file.
        env_overrides: Environment variable overrides.

    Returns:
        Merged config dict.
    """
    merged = dict(defaults)

    for key, value in loaded.items():
        if value is not None:
            merged[key] = value

    for key, value in env_overrides.items():
        if value is not None:
            merged[key] = value

    return merged
