"""Artifact path directory layout and path sanitization utilities."""

import re
from pathlib import Path


def sanitize_filename(filename: str) -> str:
    """Sanitize filename to prevent path traversal and invalid character issues."""
    name = Path(filename).name
    # Replace non-alphanumeric chars (except dot, dash, underscore) with underscore
    sanitized = re.sub(r"[^\w\.\-]", "_", name)
    return sanitized or "document.pdf"


class RunArtifactPaths:
    """Structured directory path manager for a benchmark run execution."""

    def __init__(self, base_dir: Path, run_id: str) -> None:
        self.run_id = run_id
        self.run_dir = base_dir / run_id

        self.inputs_dir = self.run_dir / "inputs"
        self.raw_outputs_dir = self.run_dir / "raw_outputs"
        self.canonical_outputs_dir = self.run_dir / "canonical_outputs"
        self.reviewed_outputs_dir = self.run_dir / "reviewed_outputs"
        self.resource_samples_dir = self.run_dir / "resource_samples"
        self.metrics_dir = self.run_dir / "metrics"
        self.logs_dir = self.run_dir / "logs"
        self.reports_dir = self.run_dir / "reports"
        self.csv_reports_dir = self.reports_dir / "csv"

    def ensure_directories(self) -> None:
        """Create all required run output directories."""
        for d in [
            self.run_dir,
            self.inputs_dir,
            self.raw_outputs_dir,
            self.canonical_outputs_dir,
            self.reviewed_outputs_dir,
            self.resource_samples_dir,
            self.metrics_dir,
            self.logs_dir,
            self.reports_dir,
            self.csv_reports_dir,
        ]:
            d.mkdir(parents=True, exist_ok=True)

    @property
    def run_config_file(self) -> Path:
        return self.run_dir / "run_config.yaml"

    @property
    def environment_file(self) -> Path:
        return self.run_dir / "environment.json"

    @property
    def status_file(self) -> Path:
        return self.run_dir / "status.json"

    @property
    def manifest_file(self) -> Path:
        return self.run_dir / "manifest.csv"

    def engine_raw_output_dir(self, config_id: str) -> Path:
        p = self.raw_outputs_dir / config_id
        p.mkdir(parents=True, exist_ok=True)
        return p

    def engine_canonical_output_dir(self, config_id: str) -> Path:
        p = self.canonical_outputs_dir / config_id
        p.mkdir(parents=True, exist_ok=True)
        return p

    def engine_log_dir(self, config_id: str) -> Path:
        p = self.logs_dir / config_id
        p.mkdir(parents=True, exist_ok=True)
        return p
