"""Unit tests for EngineRegistry."""

import pytest

from document_benchmark.core.contracts import EngineSpec
from document_benchmark.core.engine_registry import EngineRegistry
from document_benchmark.core.exceptions import EngineUnavailableError
from document_benchmark.core.statuses import EngineStatus
from document_benchmark.engines.mock_engine import MockEngine


def test_registry_registration():
    reg = EngineRegistry()
    spec = EngineSpec(engine_id="mock", config_id="mock_cfg")
    reg.register_config(spec)

    cfg = reg.get_config("mock_cfg")
    assert cfg is not None
    assert cfg.config_id == "mock_cfg"


def test_registry_create_engine():
    reg = EngineRegistry()
    spec = EngineSpec(engine_id="mock", config_id="mock_cfg")
    reg.register_config(spec)

    engine = reg.create_engine("mock_cfg")
    assert isinstance(engine, MockEngine)


def test_registry_healthcheck():
    reg = EngineRegistry()
    spec = EngineSpec(engine_id="mock", config_id="mock_cfg")
    reg.register_config(spec)

    health = reg.healthcheck_config("mock_cfg")
    assert health.available is True
    assert health.status == EngineStatus.SUCCESS


def test_registry_unregistered_config():
    reg = EngineRegistry()
    with pytest.raises(EngineUnavailableError):
        reg.create_engine("non_existent_config")
