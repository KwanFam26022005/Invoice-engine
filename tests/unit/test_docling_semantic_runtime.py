"""Unit tests for Docling semantic runtime routing without loading model weights."""

from pathlib import Path

from document_engine.workers.docling_semantic_worker import (
    artifacts_ready,
    semantic_runtime_config,
)


def test_cpu_runtime_disables_8bit_quantization_even_when_requested():
    config = semantic_runtime_config(
        {
            "device": "cpu",
            "load_in_8bit": True,
            "num_threads": 2,
        }
    )

    assert config["actual_device"] == "cpu"
    assert config["resource_ready"] is True
    assert config["load_in_8bit"] is False
    assert config["num_threads"] == 2


def test_unsupported_runtime_device_is_not_ready():
    config = semantic_runtime_config({"device": "tpu"})

    assert config["resource_ready"] is False
    assert config["resource_error"] == "UNSUPPORTED_SEMANTIC_DEVICE"


def test_artifacts_ready_requires_weight_and_model_config(tmp_path: Path):
    assert artifacts_ready(tmp_path) is False

    (tmp_path / "config.json").write_text("{}", encoding="utf-8")
    assert artifacts_ready(tmp_path) is False

    (tmp_path / "model.safetensors").write_bytes(b"synthetic")
    assert artifacts_ready(tmp_path) is True
