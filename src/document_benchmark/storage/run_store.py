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
        with open(paths.run_config_file, "w", encoding="utf-8") as f:
            yaml.safe_dump(spec.model_dump(mode="json"), f, default_flow_style=False)

    def save_environment(self, paths: RunArtifactPaths, env_data: dict[str, Any]) -> None:
        with open(paths.environment_file, "w", encoding="utf-8") as f:
            json.dump(env_data, f, indent=2, ensure_ascii=False)

    def save_status(self, paths: RunArtifactPaths, status_data: dict[str, Any]) -> None:
        with open(paths.status_file, "w", encoding="utf-8") as f:
            json.dump(status_data, f, indent=2, ensure_ascii=False, default=str)

    def save_manifest(self, paths: RunArtifactPaths, documents: list[DocumentInput]) -> None:
        fieldnames = [
            "document_id",
            "filename",
            "sha256",
            "page_count",
            "mime_type",
            "path",
        ]
        with open(paths.manifest_file, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for doc in documents:
                writer.writerow(
                    {
                        "document_id": doc.document_id,
                        "filename": doc.filename,
                        "sha256": doc.sha256,
                        "page_count": doc.page_count,
                        "mime_type": doc.mime_type,
                        "path": doc.path,
                    }
                )

    def save_raw_result(
        self, paths: RunArtifactPaths, config_id: str, result: RawExtractionResult
    ) -> Path:
        out_dir = paths.engine_raw_output_dir(config_id)
        file_path = out_dir / f"{result.document_id}.json"
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(result.model_dump_json(indent=2))
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
        out_file = (
            paths.resource_samples_dir / f"{config_id}_{document_id}_run{run_index}.json"
        )
        data = {
            "config_id": config_id,
            "document_id": document_id,
            "run_index": run_index,
            "summary": summary.model_dump(),
            "samples": [s.model_dump() for s in samples],
        }
        with open(out_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def load_raw_result(
        self, paths: RunArtifactPaths, config_id: str, document_id: str
    ) -> RawExtractionResult | None:
        file_path = paths.engine_raw_output_dir(config_id) / f"{document_id}.json"
        if not file_path.exists():
            return None
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return RawExtractionResult(**data)
