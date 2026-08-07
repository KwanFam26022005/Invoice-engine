"""Evidence grounding for semantic extraction candidates.

The grounder is deliberately deterministic. Semantic/VLM output remains a candidate
until its value can be located in DocumentIR blocks or table cells. Financial and
identifier-like fields never use fuzzy matching.
"""

from dataclasses import dataclass
from decimal import Decimal
from difflib import SequenceMatcher
from enum import Enum
import re
from typing import Iterable, List, Optional, Tuple

from pydantic import BaseModel, Field

from document_engine.extraction.normalizer import (
    normalize_tax_id,
    normalize_text,
    parse_date,
    parse_decimal,
)
from document_engine.ir.models import DocumentIR, EvidenceReference
from document_engine.semantic.contracts import (
    SemanticCandidate,
    SemanticCandidateStatus,
    SemanticEvidenceHint,
    SemanticExtractionResult,
)


class GroundingStatus(str, Enum):
    GROUNDED = "grounded"
    UNSUPPORTED = "unsupported"
    ABSTAINED = "abstained"


class GroundingMethod(str, Enum):
    EXACT_SOURCE = "exact_source"
    NORMALIZED_TEXT = "normalized_text"
    TAX_ID_CANONICAL = "tax_id_canonical"
    DECIMAL_CANONICAL = "decimal_canonical"
    DATE_CANONICAL = "date_canonical"
    FUZZY_TEXT = "fuzzy_text"
    NONE = "none"


class GroundedSemanticCandidate(BaseModel):
    candidate: SemanticCandidate
    grounding_status: GroundingStatus
    match_method: GroundingMethod = GroundingMethod.NONE
    match_score: float = Field(default=0.0, ge=0.0, le=1.0)
    evidence_references: List[EvidenceReference] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)


class SemanticGroundingReport(BaseModel):
    document_id: str
    extractor_id: str
    candidates: List[GroundedSemanticCandidate] = Field(default_factory=list)

    @property
    def grounded_count(self) -> int:
        return sum(item.grounding_status == GroundingStatus.GROUNDED for item in self.candidates)

    @property
    def unsupported_count(self) -> int:
        return sum(
            item.grounding_status == GroundingStatus.UNSUPPORTED for item in self.candidates
        )

    @property
    def abstained_count(self) -> int:
        return sum(item.grounding_status == GroundingStatus.ABSTAINED for item in self.candidates)


@dataclass(frozen=True)
class _SourceSpan:
    page_number: int
    text: str
    block_id: Optional[str] = None
    table_id: Optional[str] = None
    cell_id: Optional[str] = None
    bbox: Optional[List[float]] = None

    @property
    def identity(self) -> Tuple[object, ...]:
        return (
            self.page_number,
            self.block_id,
            self.table_id,
            self.cell_id,
            self.text,
        )


class EvidenceGrounder:
    """Ground scalar semantic candidates against immutable DocumentIR evidence."""

    def __init__(self, fuzzy_threshold: float = 0.92):
        if not 0.0 <= fuzzy_threshold <= 1.0:
            raise ValueError("fuzzy_threshold must be between 0 and 1.")
        self.fuzzy_threshold = fuzzy_threshold

    def ground_result(
        self,
        result: SemanticExtractionResult,
        document_ir: DocumentIR,
    ) -> SemanticGroundingReport:
        if result.document_id != document_ir.document_id:
            raise ValueError("Semantic extraction result and DocumentIR must reference one document.")

        return SemanticGroundingReport(
            document_id=document_ir.document_id,
            extractor_id=result.extractor_id,
            candidates=[self.ground(candidate, document_ir) for candidate in result.candidates],
        )

    def ground(
        self,
        candidate: SemanticCandidate,
        document_ir: DocumentIR,
    ) -> GroundedSemanticCandidate:
        if candidate.status == SemanticCandidateStatus.ABSTAINED:
            return GroundedSemanticCandidate(
                candidate=candidate,
                grounding_status=GroundingStatus.ABSTAINED,
            )
        if candidate.status == SemanticCandidateStatus.UNSUPPORTED or candidate.value is None:
            return GroundedSemanticCandidate(
                candidate=candidate,
                grounding_status=GroundingStatus.UNSUPPORTED,
                warnings=["Candidate was already unsupported or did not contain a value."],
            )
        if isinstance(candidate.value, (dict, list, tuple, set)):
            return GroundedSemanticCandidate(
                candidate=candidate,
                grounding_status=GroundingStatus.UNSUPPORTED,
                warnings=[
                    "Compound semantic candidates must be decomposed into atomic field candidates before grounding."
                ],
            )

        all_sources = list(self._iter_sources(document_ir))
        hinted_sources = self._sources_for_hints(all_sources, candidate.evidence_hints)
        ordered_sources = self._deduplicate([*hinted_sources, *all_sources])

        for source in ordered_sources:
            matched = self._match_candidate(candidate, source.text)
            if matched is None:
                continue
            method, score = matched
            evidence = EvidenceReference(
                document_id=document_ir.document_id,
                page_number=source.page_number,
                block_id=source.block_id,
                table_id=source.table_id,
                cell_id=source.cell_id,
                bbox=source.bbox,
                source_text=source.text,
                parser_id=document_ir.provenance.parser_id,
                parser_version=document_ir.provenance.parser_version,
                confidence=score,
            )
            return GroundedSemanticCandidate(
                candidate=candidate,
                grounding_status=GroundingStatus.GROUNDED,
                match_method=method,
                match_score=score,
                evidence_references=[evidence],
            )

        return GroundedSemanticCandidate(
            candidate=candidate,
            grounding_status=GroundingStatus.UNSUPPORTED,
            warnings=["Candidate value could not be grounded in DocumentIR."],
        )

    def _iter_sources(self, document_ir: DocumentIR) -> Iterable[_SourceSpan]:
        for page in document_ir.pages:
            for block in page.blocks:
                if block.text.strip():
                    yield _SourceSpan(
                        page_number=page.page_number,
                        text=block.text,
                        block_id=block.block_id,
                        bbox=block.geometry.bbox if block.geometry else None,
                    )
            for table in page.tables:
                for cell in table.cells:
                    if cell.text.strip():
                        yield _SourceSpan(
                            page_number=table.page_number,
                            text=cell.text,
                            table_id=table.table_id,
                            cell_id=cell.cell_id,
                            bbox=cell.geometry.bbox if cell.geometry else None,
                        )

    def _sources_for_hints(
        self,
        sources: List[_SourceSpan],
        hints: List[SemanticEvidenceHint],
    ) -> List[_SourceSpan]:
        if not hints:
            return []
        return [source for source in sources if any(self._hint_matches(source, hint) for hint in hints)]

    @staticmethod
    def _hint_matches(source: _SourceSpan, hint: SemanticEvidenceHint) -> bool:
        if hint.page_number is not None and source.page_number != hint.page_number:
            return False
        if hint.block_id is not None and source.block_id != hint.block_id:
            return False
        if hint.table_id is not None and source.table_id != hint.table_id:
            return False
        if hint.cell_id is not None and source.cell_id != hint.cell_id:
            return False
        if hint.bbox is not None:
            if source.bbox is None or len(source.bbox) != len(hint.bbox):
                return False
            if any(abs(left - right) > 1.0 for left, right in zip(source.bbox, hint.bbox)):
                return False
        return any(
            value is not None
            for value in (
                hint.page_number,
                hint.block_id,
                hint.table_id,
                hint.cell_id,
                hint.bbox,
            )
        )

    @staticmethod
    def _deduplicate(sources: List[_SourceSpan]) -> List[_SourceSpan]:
        output: List[_SourceSpan] = []
        seen = set()
        for source in sources:
            if source.identity in seen:
                continue
            seen.add(source.identity)
            output.append(source)
        return output

    def _match_candidate(
        self,
        candidate: SemanticCandidate,
        source_text: str,
    ) -> Optional[Tuple[GroundingMethod, float]]:
        field_path = candidate.field_path.lower()

        if "tax_id" in field_path:
            target_tax_id, _, _ = normalize_tax_id(str(candidate.value))
            if target_tax_id:
                for token in self._tax_id_tokens(source_text):
                    source_tax_id, _, _ = normalize_tax_id(token)
                    if source_tax_id and source_tax_id == target_tax_id:
                        return GroundingMethod.TAX_ID_CANONICAL, 1.0
            return None

        if "date" in field_path:
            target_date, _, _ = parse_date(str(candidate.value))
            if target_date:
                for line in self._logical_lines(source_text):
                    source_date, _, _ = parse_date(line)
                    if source_date and source_date == target_date:
                        return GroundingMethod.DATE_CANONICAL, 1.0
            return None

        if self._is_numeric_field(field_path):
            target_decimal = self._candidate_decimal(candidate.value)
            if target_decimal is not None:
                for token in self._numeric_tokens(source_text):
                    source_decimal, _, _ = parse_decimal(token)
                    if source_decimal is not None and source_decimal == target_decimal:
                        return GroundingMethod.DECIMAL_CANONICAL, 1.0
            return None

        probe = str(candidate.value).strip()
        if not probe:
            return None

        identifier_field = self._is_identifier_field(field_path)
        if identifier_field and not self._structured_identifier_occurs(probe, source_text):
            return None

        if self._text_occurs(probe, source_text, identifier_field):
            return GroundingMethod.EXACT_SOURCE, 1.0

        source_norm = self._normalize_for_match(source_text)
        probe_norm = self._normalize_for_match(probe)
        if probe_norm and (
            not identifier_field
            or self._structured_identifier_occurs(probe_norm, source_norm)
        ) and self._text_occurs(probe_norm, source_norm, identifier_field):
            return GroundingMethod.NORMALIZED_TEXT, 1.0

        if self._allows_fuzzy(field_path):
            target = probe_norm
            if len(target) >= 6:
                best = 0.0
                for line in self._logical_lines(source_text):
                    source = self._normalize_for_match(line)
                    if not source:
                        continue
                    best = max(best, SequenceMatcher(None, target, source).ratio())
                if best >= self.fuzzy_threshold:
                    return GroundingMethod.FUZZY_TEXT, best

        return None

    @staticmethod
    def _text_occurs(probe: str, source: str, identifier_field: bool) -> bool:
        if probe == source.strip():
            return True
        if not identifier_field:
            return probe in source
        return re.search(rf"(?<!\w){re.escape(probe)}(?!\w)", source) is not None

    @staticmethod
    def _structured_identifier_occurs(probe: str, source: str) -> bool:
        """Match an identifier as a complete structured token, never a suffix."""
        if probe.isdigit():
            if source.strip() == probe:
                return True
            if len(probe) == 1:
                return False
            return re.search(
                rf"(?<![\w./-]){re.escape(probe)}(?![\w./-])", source
            ) is not None
        return re.search(rf"(?<![\w-]){re.escape(probe)}(?![\w-])", source) is not None

    @staticmethod
    def _normalize_for_match(value: str) -> str:
        clean, _, _ = normalize_text(value)
        return clean.casefold()

    @staticmethod
    def _logical_lines(value: str) -> List[str]:
        lines = [line.strip() for line in value.splitlines() if line.strip()]
        return lines or [value.strip()]

    @staticmethod
    def _tax_id_tokens(value: str) -> List[str]:
        tokens = re.findall(r"(?<!\d)(?:\d[\s-]*){10,13}(?!\d)", value)
        return [token.strip() for token in tokens]

    @staticmethod
    def _numeric_tokens(value: str) -> List[str]:
        return [
            token.strip()
            for token in re.findall(r"(?<![\w-])-?\d[\d\s.,]*(?!\w)", value)
            if token.strip()
        ]

    @staticmethod
    def _candidate_decimal(value: object) -> Optional[Decimal]:
        if isinstance(value, Decimal):
            return value
        if isinstance(value, (int, float)):
            return Decimal(str(value))
        parsed, _, _ = parse_decimal(str(value))
        return parsed

    @staticmethod
    def _is_numeric_field(field_path: str) -> bool:
        tokens = (
            "amount",
            "total",
            "price",
            "quantity",
            "reading",
            "consumption",
            "rate",
            "subtotal",
            "discount",
        )
        return any(token in field_path for token in tokens)

    @staticmethod
    def _is_identifier_field(field_path: str) -> bool:
        tokens = ("number", "serial", "code", "tax_id")
        return any(token in field_path for token in tokens)

    @staticmethod
    def _allows_fuzzy(field_path: str) -> bool:
        denied_tokens = (
            "number",
            "tax_id",
            "amount",
            "total",
            "price",
            "quantity",
            "date",
            "period",
            "serial",
            "code",
            "reading",
            "consumption",
            "rate",
            "tax",
        )
        return not any(token in field_path for token in denied_tokens)
