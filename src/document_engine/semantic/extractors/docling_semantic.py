"""Local-only Docling schema-conditioned semantic extractor adapter."""

import os
from typing import Optional

from document_engine.core.models import DocumentFamilyType
from document_engine.runtime.worker_client import WorkerClient
from document_engine.runtime.worker_contracts import WorkerRequest
from document_engine.semantic.contracts import (
    SemanticExtractionRequest,
    SemanticExtractionResult,
)
from document_engine.semantic.schema_registry import (
    get_semantic_schema,
    supports_semantic_schema,
)


class DoclingSemanticExtractor:
    extractor_id = "docling_semantic"

    def __init__(self, worker_client: Optional[WorkerClient] = None, timeout: float = 180.0):
        self.worker_client = worker_client or WorkerClient(default_timeout=timeout)
        self.timeout = timeout

    def supports(
        self,
        family: DocumentFamilyType,
        target_schema_name: str,
        document_ir,
    ) -> bool:
        return supports_semantic_schema(family, target_schema_name)

    def healthcheck(self, allow_model_download: bool = False):
        request = WorkerRequest(
            request_id="docling_semantic_healthcheck",
            parser_id=self.extractor_id,
            operation="healthcheck",
            options={
                "artifacts_path": os.getenv("DOCLING_SEMANTIC_ARTIFACTS_PATH", ""),
            },
            allow_model_download=allow_model_download,
        )
        return self.worker_client.execute_worker(request, timeout=self.timeout)

    def extract(self, request: SemanticExtractionRequest) -> SemanticExtractionResult:
        if request.policy.allow_network:
            return self._failure(request, "NETWORK_POLICY_REJECTED")

        try:
            spec = get_semantic_schema(request.family, request.target_schema_name)
        except KeyError:
            return self._failure(request, "UNSUPPORTED_SEMANTIC_SCHEMA")

        worker_request = WorkerRequest(
            request_id=f"semantic_{request.document_id}",
            parser_id=self.extractor_id,
            operation="extract",
            input_path=request.document_ir.source_document.path,
            document_id=request.document_id,
            source_sha256=request.document_ir.source_document.sha256,
            page_count=request.document_ir.source_document.page_count,
            options={
                "family": request.family.value,
                "schema_name": spec.schema_name,
                "template": spec.template_copy(),
                "artifacts_path": os.getenv("DOCLING_SEMANTIC_ARTIFACTS_PATH", ""),
                "max_candidates_per_field": request.policy.max_candidates_per_field,
            },
            allow_model_download=False,
        )
        response = self.worker_client.execute_worker(worker_request, timeout=self.timeout)
        if not response.success or response.semantic_result_dict is None:
            return self._failure(
                request,
                response.error_type or "DOCLING_SEMANTIC_WORKER_FAILED",
            )

        try:
            result = SemanticExtractionResult.model_validate(response.semantic_result_dict)
        except Exception:
            return self._failure(request, "INVALID_SEMANTIC_WORKER_RESULT")

        if result.document_id != request.document_id or result.family != request.family:
            return self._failure(request, "SEMANTIC_WORKER_IDENTITY_MISMATCH")

        return self._apply_candidate_limit(result, request.policy.max_candidates_per_field)

    @staticmethod
    def _failure(request: SemanticExtractionRequest, code: str) -> SemanticExtractionResult:
        return SemanticExtractionResult(
            extractor_id="docling_semantic",
            document_id=request.document_id,
            family=request.family,
            success=False,
            error_code=code,
        )

    @staticmethod
    def _apply_candidate_limit(
        result: SemanticExtractionResult,
        max_candidates_per_field: int,
    ) -> SemanticExtractionResult:
        counts = {}
        kept = []
        dropped = 0
        for candidate in result.candidates:
            current = counts.get(candidate.field_path, 0)
            if current >= max_candidates_per_field:
                dropped += 1
                continue
            counts[candidate.field_path] = current + 1
            kept.append(candidate)
        result.candidates = kept
        if dropped:
            result.warnings.append("CANDIDATE_LIMIT_APPLIED")
        return result
