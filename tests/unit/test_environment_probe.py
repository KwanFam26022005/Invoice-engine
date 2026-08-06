"""Unit tests for environment_probe."""

from document_benchmark.runner.environment_probe import probe_environment


def test_probe_environment_fields():
    env = probe_environment()

    assert "os" in env
    assert "python_version" in env
    assert "cpu_logical_cores" in env
    assert "ram_total_mb" in env
    assert "gpu_available" in env
    assert "package_versions" in env
    assert isinstance(env["package_versions"], dict)
