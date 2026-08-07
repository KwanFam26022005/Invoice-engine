"""Workspace settings and configuration management for Document Engine."""

import os
from pathlib import Path
from typing import Any, Dict, Optional
import yaml
from pydantic import BaseModel, Field


class WorkspacePaths(BaseModel):
    root: Path
    inbox: Path
    database: Path
    database_file: Path
    runs: Path
    exports: Path
    review: Path
    logs: Path
    cache: Path

    def ensure_directories(self) -> None:
        """Create all workspace directories if they do not exist."""
        for path in [
            self.root,
            self.inbox,
            self.database,
            self.runs,
            self.exports,
            self.review,
            self.logs,
            self.cache,
        ]:
            path.mkdir(parents=True, exist_ok=True)


class AppConfig(BaseModel):
    workspace_root: str = Field(
        default_factory=lambda: os.getenv(
            "DOCUMENT_ENGINE_HOME", r"D:\Documents-engine\workspace"
        )
    )
    database_name: str = "document_engine.duckdb"
    default_parser_policy: Dict[str, str] = Field(
        default_factory=lambda: {
            "native_pdf": "pymupdf_native",
            "scan_pdf": "docling_ocr",
            "mixed_pdf": "docling_ocr",
            "fallback": "paddleocr_vl",
        }
    )
    fallback_enabled: bool = True
    max_pages: int = 200
    max_file_size_mb: float = 100.0
    batch_concurrency: int = 1
    validation_tolerance: float = 0.01
    excel_options: Dict[str, Any] = Field(
        default_factory=lambda: {
            "sanitize_formulas": True,
            "auto_filter": True,
            "freeze_panes": True,
        }
    )

    @classmethod
    def load_from_file(cls, config_path: Optional[Path] = None) -> "AppConfig":
        if config_path is None:
            config_path = Path(
                os.getenv("DOCUMENT_ENGINE_CONFIG", "configs/app.yaml")
            )
        if config_path.exists():
            with open(config_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            return cls(**data)
        return cls()


def get_workspace_paths(
    workspace_root: Optional[Path] = None,
) -> WorkspacePaths:
    if workspace_root is None:
        env_root = os.getenv("DOCUMENT_ENGINE_HOME")
        if env_root:
            workspace_root = Path(env_root)
        else:
            workspace_root = Path(r"D:\Documents-engine\workspace")
    workspace_root = workspace_root.resolve()
    db_dir = workspace_root / "database"
    return WorkspacePaths(
        root=workspace_root,
        inbox=workspace_root / "inbox",
        database=db_dir,
        database_file=db_dir / "document_engine.duckdb",
        runs=workspace_root / "runs",
        exports=workspace_root / "exports",
        review=workspace_root / "review",
        logs=workspace_root / "logs",
        cache=workspace_root / "cache",
    )
