"""Small runtime helpers shared by optional document-engine adapters."""

from __future__ import annotations

from importlib import metadata
from pathlib import Path
from typing import Any


def package_version(distribution_name: str) -> str | None:
    """Return the installed distribution version without importing the package."""
    try:
        return metadata.version(distribution_name)
    except metadata.PackageNotFoundError:
        return None


def runtime_identity(instance: Any) -> dict[str, str]:
    """Describe the concrete runtime class used for inference."""
    cls = type(instance)
    return {
        "runtime_module": cls.__module__,
        "runtime_class": cls.__qualname__,
    }


def json_safe(value: Any) -> Any:
    """Convert common model-result objects into JSON-serializable values."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [json_safe(item) for item in value]
    if hasattr(value, "tolist"):
        try:
            return json_safe(value.tolist())
        except Exception:
            pass
    if hasattr(value, "item"):
        try:
            return json_safe(value.item())
        except Exception:
            pass
    if hasattr(value, "model_dump"):
        try:
            return json_safe(value.model_dump(mode="json"))
        except Exception:
            pass
    return str(value)
