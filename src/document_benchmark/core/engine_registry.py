"""Engine registry for discovering, registering, and instantiating adapters."""

import importlib

import yaml

from document_benchmark.core.contracts import EngineHealth, EngineSpec
from document_benchmark.core.exceptions import EngineUnavailableError
from document_benchmark.core.statuses import EngineStatus
from document_benchmark.engines.base import DocumentEngine
from document_benchmark.engines.mock_engine import MockEngine


class EngineRegistry:
    """Central registry for document extraction engines and versioned configs."""

    def __init__(self) -> None:
        self._engine_classes: dict[str, type[DocumentEngine]] = {}
        self._configs: dict[str, EngineSpec] = {}
        self.register_engine_class("mock", MockEngine)

    def register_engine_class(self, engine_id: str, cls: type[DocumentEngine]) -> None:
        self._engine_classes[engine_id] = cls

    def register_config(self, spec: EngineSpec) -> None:
        self._configs[spec.config_id] = spec

    def load_config_from_file(self, config_path: str) -> EngineSpec:
        with open(config_path, "r", encoding="utf-8") as stream:
            data = yaml.safe_load(stream)
        spec = EngineSpec(**data)
        self.register_config(spec)
        return spec

    def get_config(self, config_id: str) -> EngineSpec | None:
        return self._configs.get(config_id)

    def list_configs(self, enabled_only: bool = False) -> list[EngineSpec]:
        configs = list(self._configs.values())
        return [config for config in configs if config.enabled] if enabled_only else configs

    def create_engine(self, config_id: str) -> DocumentEngine:
        spec = self._configs.get(config_id)
        if spec is None:
            raise EngineUnavailableError(
                f"Configuration config_id='{config_id}' is not registered.",
                code="CONFIG_NOT_FOUND",
            )
        if spec.engine_id not in self._engine_classes:
            self._try_lazy_register(spec.engine_id)
        if spec.engine_id not in self._engine_classes:
            raise EngineUnavailableError(
                f"Engine '{spec.engine_id}' is not registered.",
                engine_id=spec.engine_id,
            )
        return self._engine_classes[spec.engine_id](spec)

    def healthcheck_config(self, config_id: str) -> EngineHealth:
        spec = self._configs.get(config_id)
        if spec is None:
            return EngineHealth(
                engine_id="unknown",
                config_id=config_id,
                status=EngineStatus.UNAVAILABLE,
                available=False,
                error_message=f"Configuration '{config_id}' not found.",
            )
        if not spec.enabled:
            return EngineHealth(
                engine_id=spec.engine_id,
                config_id=config_id,
                status=EngineStatus.UNAVAILABLE,
                available=False,
                error_message="Engine configuration is disabled.",
            )

        try:
            engine = self.create_engine(config_id)
            health = engine.healthcheck()
            engine.close()
            return health
        except Exception as exc:
            return EngineHealth(
                engine_id=spec.engine_id,
                config_id=config_id,
                status=EngineStatus.UNAVAILABLE,
                available=False,
                error_message=str(exc),
            )

    def _try_lazy_register(self, engine_id: str) -> None:
        module_map = {
            "docling": ("document_benchmark.engines.docling_engine", "DoclingEngine"),
            "ppstructure_v3": (
                "document_benchmark.engines.ppstructure_engine",
                "PPStructureV3Engine",
            ),
            "ppstructure_v2_legacy": (
                "document_benchmark.engines.ppstructure_v2_engine",
                "PPStructureV2LegacyEngine",
            ),
            "paddleocr_vl": (
                "document_benchmark.engines.paddleocr_vl_engine",
                "PaddleOCRVLEngine",
            ),
            "sparrow": ("document_benchmark.engines.sparrow_engine", "SparrowEngine"),
        }
        mapping = module_map.get(engine_id)
        if mapping is None:
            return
        module_path, class_name = mapping
        try:
            module = importlib.import_module(module_path)
            self.register_engine_class(engine_id, getattr(module, class_name))
        except Exception:
            return


registry = EngineRegistry()
