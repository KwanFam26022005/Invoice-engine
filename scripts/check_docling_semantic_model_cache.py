"""Privacy-safe readiness check for locally prepared Docling semantic model assets."""

import json
import os
from pathlib import Path
import sys

WEIGHT_SUFFIXES = {".safetensors", ".bin", ".pt", ".onnx"}


def inspect_cache(path: Path) -> dict:
    if not path.is_dir():
        return {
            "exists": False,
            "ready": False,
            "weight_file_count": 0,
            "config_file_count": 0,
            "total_weight_bytes": 0,
        }

    weight_files = []
    config_files = []
    try:
        for item in path.rglob("*"):
            if not item.is_file():
                continue
            if item.suffix.lower() in WEIGHT_SUFFIXES:
                weight_files.append(item)
            if item.name in {"config.json", "preprocessor_config.json", "processor_config.json"}:
                config_files.append(item)
    except OSError:
        return {
            "exists": True,
            "ready": False,
            "weight_file_count": 0,
            "config_file_count": 0,
            "total_weight_bytes": 0,
        }

    total_weight_bytes = 0
    for item in weight_files:
        try:
            total_weight_bytes += item.stat().st_size
        except OSError:
            pass

    return {
        "exists": True,
        "ready": bool(weight_files and config_files),
        "weight_file_count": len(weight_files),
        "config_file_count": len(config_files),
        "total_weight_bytes": total_weight_bytes,
    }


def main() -> int:
    raw = os.getenv("DOCLING_SEMANTIC_ARTIFACTS_PATH")
    if not raw:
        print(json.dumps({"configured": False, "ready": False}, indent=2))
        return 2

    report = inspect_cache(Path(raw).expanduser().resolve())
    report["configured"] = True
    print(json.dumps(report, indent=2))
    return 0 if report["ready"] else 2


if __name__ == "__main__":
    sys.exit(main())
