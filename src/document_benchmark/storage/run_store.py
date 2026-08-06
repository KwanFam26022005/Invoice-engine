"""Storage repository for persisting benchmark run artifacts."""

import csv
import json
from pathlib import Path
from typing import Any

import yaml

from document_benchmark.core.contracts import (
    BenchmarkRunSpec,
    DocumentInput,
    RawExtractionResult,
    ResourceSample,
    ResourceSummary,
)
from document_benchmark.storage.artifact_paths import RunArtifactPaths


class RunStore:
    """Manages reading and writing run artifacts to disk."""

    def __init__(self, runs_root: str = "runs") -> None:
        self.runs_root = Path(runs_root)

    def get_paths(self, run_id: str) -> RunArtifactPaths:
        paths = RunArtifactPaths(self.runs_root, run_id)
        paths.ensure_directories()
        return paths

    def save_run_spec(self, paths: RunArtifactPaths, spec: BenchmarkRunSpec) -> None:
        with paths.run_config_file.open("w", encoding="utf-8") as file:
            yaml.safe_dump(spec.model_dump(mode="json"), file, default_flow_style=False)

    def save_environment(self, paths: RunArtifactPaths, env_data: dict[str, Any]) -> None:
        paths.environment_file.write_text(
            json.dumps(env_data, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    def save_status(self, paths: RunArtifactPaths, status_data: dict[str, Any]) -> None:
        paths.status_file.write_text(
            json.dumps(status_data, indent=2, ensure_ascii=False, default=str),
            encoding="utf-8",
        )

    def save_manifest(self, paths: RunArtifactPaths, documents: list[DocumentInput]) -> None:
        fieldnames = [
            "document_id",
            "filename",
            "sha256",
            "page_count",
            "mime_type",
            "path",
        ]
        with paths.manifest_file.open("w", encoding="utf-8", newline="") as file:
            writer = csv.DictWriter(file, fieldnames=fieldnames)
            writer.writeheader()
            for document in documents:
                writer.writerow(
                    {
                        "document_id": document.document_id,
                        "filename": document.filename,
                        "sha256": document.sha256,
                        "page_count": document.page_count,
                        "mime_type": document.mime_type,
                        "path": document.path,
                    }
                )

    def save_raw_result(
        self,
        paths: RunArtifactPaths,
        config_id: str,
        result: RawExtractionResult,
        run_index: int | None = None,
    ) -> Path:
        """Persist one extraction result without overwriting repeat outputs."""
        document_dir = paths.engine_raw_output_dir(config_id) / result.document_id
        document_dir.mkdir(parents=True, exist_ok=True)
        filename = "result.json" if run_index is None else f"run_{run_index:03d}.json"
        file_path = document_dir / filename
        file_path.write_text(result.model_dump_json(indent=2), encoding="utf-8")
        return file_path

    def save_resource_samples(
        self,
        paths: RunArtifactPaths,
        config_id: str,
        document_id: str,
        run_index: int,
        samples: list[ResourceSample],
        summary: ResourceSummary,
    ) -> None:
        out_file = paths.resource_samples_dir / f"{config_id}_{document_id}_run{run_index}.json"
        data = {
            "config_id": config_id,
            "document_id": document_id,
            "run_index": run_index,
            "summary": summary.model_dump(),
            "samples": [sample.model_dump() for sample in samples],
        }
        out_file.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    def load_raw_result(
        self,
        paths: RunArtifactPaths,
        config_id: str,
        document_id: str,
        run_index: int | None = None,
    ) -> RawExtractionResult | None:
        document_dir = paths.engine_raw_output_dir(config_id) / document_id
        filename = "result.json" if run_index is None else f"run_{run_index:03d}.json"
        file_path = document_dir / filename
        if not file_path.exists() and run_index is None:
            candidates = sorted(document_dir.glob("run_*.json")) if document_dir.exists() else []
            file_path = candidates[-1] if candidates else file_path
        if not file_path.exists():
            return None
        return RawExtractionResult(**json.loads(file_path.read_text(encoding="utf-8")))
