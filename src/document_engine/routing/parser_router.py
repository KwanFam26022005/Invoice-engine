"""Profile-aware Parser Router dispatches documents to optimal parsers and handles fallback policy."""

from typing import Any, Dict, Optional
from pydantic import BaseModel, Field

from document_engine.core.models import PDFProfileType
from document_engine.ir.models import DocumentParseResult, DocumentProfile, SourceDocument
from document_engine.parsers.base import DocumentParser
from document_engine.parsers.registry import ParserRegistry, default_registry


class RoutingDecision(BaseModel):
    selected_parser: str
    selection_reason: str
    profile_signals: Dict[str, Any] = Field(default_factory=dict)
    fallback_trigger: Optional[str] = None
    attempt_number: int = 1


class ParserRoutingOutcome(BaseModel):
    primary_result: DocumentParseResult
    fallback_result: Optional[DocumentParseResult] = None
    selected_result: DocumentParseResult
    selection_reason: str
    routing_decision: RoutingDecision


class ParserRouter:
    def __init__(
        self,
        registry: Optional[ParserRegistry] = None,
        policy: Optional[Dict[str, str]] = None,
    ):
        self.registry = registry or default_registry
        self.policy = policy or {
            "native_pdf": "pymupdf_native",
            "scan_pdf": "docling_ocr",
            "mixed_pdf": "docling_ocr",
            "fallback": "paddleocr_vl",
        }

    def route_and_parse(
        self,
        document: SourceDocument,
        profile: DocumentProfile,
        enable_fallback: bool = True,
        forced_parser: Optional[str] = None,
    ) -> ParserRoutingOutcome:
        # 1. Determine primary parser ID
        if forced_parser:
            primary_parser_id = forced_parser
            reason = f"User explicitly requested parser '{forced_parser}'."
        else:
            profile_key = profile.pdf_profile.value
            primary_parser_id = self.policy.get(profile_key, "pymupdf_native")
            reason = f"Selected '{primary_parser_id}' based on profile '{profile_key}'."

        decision = RoutingDecision(
            selected_parser=primary_parser_id,
            selection_reason=reason,
            profile_signals={
                "pdf_profile": profile.pdf_profile.value,
                "has_text_layer": profile.has_text_layer,
                "text_character_count": profile.text_character_count,
            },
            attempt_number=1,
        )

        primary_parser = self._get_available_parser(primary_parser_id)
        primary_result = primary_parser.parse(document, profile)

        # Evaluate fallback condition
        needs_fallback = self.should_trigger_fallback(primary_result, profile)

        if needs_fallback and enable_fallback and not forced_parser:
            fallback_parser_id = self.policy.get("fallback", "paddleocr_vl")
            if fallback_parser_id != primary_parser_id:
                fallback_reason = (
                    f"Primary parser '{primary_parser_id}' failed or had empty extraction; "
                    f"triggering fallback '{fallback_parser_id}'."
                )
                fallback_parser = self._get_available_parser(fallback_parser_id)
                fallback_result = fallback_parser.parse(document, profile)

                # Select best result based on structural validity and completeness
                selected_result, final_reason = self._select_best_result(
                    primary_result, fallback_result
                )

                decision.fallback_trigger = fallback_reason
                decision.attempt_number = 2

                return ParserRoutingOutcome(
                    primary_result=primary_result,
                    fallback_result=fallback_result,
                    selected_result=selected_result,
                    selection_reason=final_reason,
                    routing_decision=decision,
                )

        return ParserRoutingOutcome(
            primary_result=primary_result,
            fallback_result=None,
            selected_result=primary_result,
            selection_reason=reason,
            routing_decision=decision,
        )

    def should_trigger_fallback(
        self, result: DocumentParseResult, profile: DocumentProfile
    ) -> bool:
        if not result.success or result.document_ir is None:
            return True

        doc_ir = result.document_ir
        if not doc_ir.full_text or not doc_ir.full_text.strip():
            return True

        if profile.pdf_profile == PDFProfileType.SCAN_PDF and not profile.has_text_layer:
            # If native parser was ran on a scan PDF and extracted no real content
            if len(doc_ir.full_text.strip()) < 10:
                return True

        return False

    def _get_available_parser(self, parser_id: str) -> DocumentParser:
        try:
            parser = self.registry.get_parser(parser_id)
            health = parser.healthcheck()
            if health.healthy:
                return parser
        except Exception:
            pass

        # Fallback to PyMuPDF native if requested parser is unavailable
        return self.registry.get_parser("pymupdf_native")

    def _select_best_result(
        self, primary: DocumentParseResult, fallback: DocumentParseResult
    ) -> tuple[DocumentParseResult, str]:
        if fallback.success and fallback.document_ir and fallback.document_ir.full_text.strip():
            if not primary.success or not primary.document_ir or not primary.document_ir.full_text.strip():
                return fallback, "Selected fallback result because primary parser failed or produced empty text."
            # Compare character completeness
            p_len = len(primary.document_ir.full_text.strip())
            f_len = len(fallback.document_ir.full_text.strip())
            if f_len > p_len * 1.5:
                return fallback, f"Selected fallback result due to significantly higher text completeness ({f_len} vs {p_len} chars)."

        return primary, "Selected primary parser result."
