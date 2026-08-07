"""Profile-aware Parser Router dispatches documents to optimal parsers and handles fallback policy."""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from document_engine.core.models import PDFProfileType
from document_engine.ir.models import DocumentIR, DocumentParseResult, DocumentProfile, SourceDocument
from document_engine.parsers.base import DocumentParser
from document_engine.parsers.registry import ParserRegistry, default_registry


class ParseQualityReport(BaseModel):
    has_pages: bool = False
    nonempty_page_ratio: float = 0.0
    text_character_count: int = 0
    block_count: int = 0
    table_count: int = 0
    geometry_coverage: float = 0.0
    page_coverage: float = 0.0
    placeholder_detected: bool = False
    parse_warnings: List[str] = Field(default_factory=list)
    critical_structure_missing: bool = False

    @classmethod
    def evaluate(cls, result: DocumentParseResult, profile: DocumentProfile) -> "ParseQualityReport":
        if not result.success or not result.document_ir:
            return cls(critical_structure_missing=True)

        doc_ir: DocumentIR = result.document_ir
        if not doc_ir.pages:
            return cls(has_pages=False, critical_structure_missing=True)

        nonempty_pages = sum(1 for p in doc_ir.pages if p.text_content and p.text_content.strip())
        ratio = nonempty_pages / len(doc_ir.pages)
        char_count = len(doc_ir.full_text.strip())
        blocks_cnt = sum(len(p.blocks) for p in doc_ir.pages)
        tables_cnt = sum(len(p.tables) for p in doc_ir.pages)

        # Check geometry coverage
        blocks_with_bbox = sum(
            1 for p in doc_ir.pages for b in p.blocks if b.geometry is not None and b.geometry.bbox
        )
        geom_coverage = blocks_with_bbox / blocks_cnt if blocks_cnt > 0 else 0.0

        # Check placeholders
        placeholder_phrases = ["fallback page", "page content", "ocr page content", "placeholder", "synthetic"]
        placeholder_found = any(
            phrase in doc_ir.full_text.lower() for phrase in placeholder_phrases
        )

        crit_missing = False
        if profile.pdf_profile == PDFProfileType.SCAN_PDF and char_count < 10:
            crit_missing = True
        if ratio < 0.5:
            crit_missing = True

        return cls(
            has_pages=True,
            nonempty_page_ratio=ratio,
            text_character_count=char_count,
            block_count=blocks_cnt,
            table_count=tables_cnt,
            geometry_coverage=geom_coverage,
            page_coverage=ratio,
            placeholder_detected=placeholder_found,
            parse_warnings=[w.message for w in result.warnings],
            critical_structure_missing=crit_missing,
        )


class RoutingDecision(BaseModel):
    requested_parser: str
    actual_parser: str
    selection_reason: str
    profile_signals: Dict[str, Any] = Field(default_factory=dict)
    fallback_trigger: Optional[str] = None
    attempt_number: int = 1
    quality_report: Optional[ParseQualityReport] = None


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
        # Determine primary requested parser ID
        if forced_parser:
            requested_parser_id = forced_parser
            reason = f"User explicitly requested parser '{forced_parser}'."
        else:
            profile_key = profile.pdf_profile.value
            requested_parser_id = self.policy.get(profile_key, "pymupdf_native")
            reason = f"Selected '{requested_parser_id}' based on profile '{profile_key}'."

        primary_parser, actual_parser_id = self._get_parser_or_none(requested_parser_id)

        if primary_parser is None:
            # Requested parser unavailable - DO NOT silent substitute
            failed_res = DocumentParseResult(
                success=False,
                error_message=f"Requested parser '{requested_parser_id}' is unavailable.",
            )
            decision = RoutingDecision(
                requested_parser=requested_parser_id,
                actual_parser=requested_parser_id,
                selection_reason=f"Requested parser '{requested_parser_id}' is unavailable.",
                profile_signals={"pdf_profile": profile.pdf_profile.value},
                attempt_number=1,
            )

            # Trigger fallback if enabled
            if enable_fallback and not forced_parser:
                fallback_parser_id = self.policy.get("fallback", "paddleocr_vl")
                if fallback_parser_id != requested_parser_id:
                    fb_parser, fb_actual_id = self._get_parser_or_none(fallback_parser_id)
                    if fb_parser:
                        fb_res = fb_parser.parse(document, profile)
                        fb_quality = ParseQualityReport.evaluate(fb_res, profile)
                        decision.fallback_trigger = f"Primary parser '{requested_parser_id}' was unavailable; fallback to '{fallback_parser_id}'."
                        decision.attempt_number = 2
                        decision.actual_parser = fb_actual_id
                        decision.quality_report = fb_quality
                        return ParserRoutingOutcome(
                            primary_result=failed_res,
                            fallback_result=fb_res,
                            selected_result=fb_res,
                            selection_reason=f"Primary unavailable. Selected fallback '{fallback_parser_id}'.",
                            routing_decision=decision,
                        )

            return ParserRoutingOutcome(
                primary_result=failed_res,
                fallback_result=None,
                selected_result=failed_res,
                selection_reason=reason,
                routing_decision=decision,
            )

        primary_result = primary_parser.parse(document, profile)
        primary_quality = ParseQualityReport.evaluate(primary_result, profile)

        decision = RoutingDecision(
            requested_parser=requested_parser_id,
            actual_parser=actual_parser_id,
            selection_reason=reason,
            profile_signals={
                "pdf_profile": profile.pdf_profile.value,
                "has_text_layer": profile.has_text_layer,
                "text_character_count": profile.text_character_count,
            },
            attempt_number=1,
            quality_report=primary_quality,
        )

        needs_fallback = self.should_trigger_fallback(primary_result, primary_quality, profile)

        if needs_fallback and enable_fallback and not forced_parser:
            fallback_parser_id = self.policy.get("fallback", "paddleocr_vl")
            if fallback_parser_id != requested_parser_id:
                fb_parser, fb_actual_id = self._get_parser_or_none(fallback_parser_id)
                if fb_parser:
                    fallback_reason = (
                        f"Primary parser '{requested_parser_id}' failed quality gate; "
                        f"triggering fallback '{fallback_parser_id}'."
                    )
                    fallback_result = fb_parser.parse(document, profile)
                    fallback_quality = ParseQualityReport.evaluate(fallback_result, profile)

                    selected_result, final_reason = self._select_best_result(
                        primary_result, primary_quality, fallback_result, fallback_quality
                    )

                    decision.fallback_trigger = fallback_reason
                    decision.attempt_number = 2
                    if selected_result == fallback_result:
                        decision.actual_parser = fb_actual_id
                        decision.quality_report = fallback_quality

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
        self,
        result: DocumentParseResult,
        quality: ParseQualityReport,
        profile: DocumentProfile,
    ) -> bool:
        if not result.success or quality.critical_structure_missing:
            return True
        if quality.placeholder_detected:
            return True
        if quality.nonempty_page_ratio < 0.5:
            return True
        return False

    def _get_parser_or_none(self, parser_id: str) -> tuple[Optional[DocumentParser], str]:
        """Fetch parser without silent substitution."""
        try:
            parser = self.registry.get_parser(parser_id)
            health = parser.healthcheck()
            if health.healthy:
                return parser, parser_id
        except Exception:
            pass
        return None, parser_id

    def _select_best_result(
        self,
        primary: DocumentParseResult,
        primary_quality: ParseQualityReport,
        fallback: DocumentParseResult,
        fallback_quality: ParseQualityReport,
    ) -> tuple[DocumentParseResult, str]:
        """Select best parse result using structural quality report."""
        if not fallback.success:
            return primary, "Selected primary parser because fallback failed."

        if not primary.success:
            return fallback, "Selected fallback parser because primary parser failed."

        # Compare placeholder detection
        if primary_quality.placeholder_detected and not fallback_quality.placeholder_detected:
            return fallback, "Selected fallback parser because primary contained placeholder content."

        # Compare structural validity and critical structures
        if primary_quality.critical_structure_missing and not fallback_quality.critical_structure_missing:
            return fallback, "Selected fallback parser because primary was missing critical structures."

        if (
            fallback_quality.table_count > primary_quality.table_count
            and fallback_quality.nonempty_page_ratio >= primary_quality.nonempty_page_ratio
        ):
            return fallback, "Selected fallback parser due to superior table layout extraction."

        return primary, "Selected primary parser result based on structural quality evaluation."
