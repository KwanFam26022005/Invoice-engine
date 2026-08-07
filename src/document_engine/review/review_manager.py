"""Review queue lifecycle, canonical versioning, and human correction manager V2."""

from datetime import datetime, timezone
import json
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from document_engine.core.field_paths import get_field_value, set_field_value
from document_engine.core.models import ReviewStatus
from document_engine.extraction.mapper import DocumentMapper
from document_engine.schemas.family_schemas import BusinessDocumentEnvelope, FieldCandidate
from document_engine.storage.database import DuckDBStorage
from document_engine.storage.projector import RelationalProjector
from document_engine.validation.validator import BusinessValidator


class ReviewItem(BaseModel):
    review_id: str
    document_id: str
    reason: str
    status: ReviewStatus = ReviewStatus.PENDING
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    updated_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


class CanonicalVersion(BaseModel):
    version_id: str
    document_id: str
    version_number: int
    source: str  # machine_extracted, human_corrected
    canonical_payload_json: str
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    reviewer: str = "human_reviewer"
    parent_version_id: Optional[str] = None


class CorrectionRecord(BaseModel):
    correction_id: str
    document_id: str
    canonical_version_before: Optional[str] = None
    canonical_version_after: Optional[str] = None
    field_path: str
    old_value: Optional[str] = None
    new_value: str
    reviewer: str = "human_reviewer"
    reason: str = "manual_correction"
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


class ReviewManager:
    """Manages document review queue lifecycle and versioned human corrections."""

    def __init__(self, db_storage: DuckDBStorage):
        self.db = db_storage
        self.validator = BusinessValidator()
        self.mapper = DocumentMapper()
        self.projector = RelationalProjector()

    def list_pending_reviews(self) -> List[Dict[str, Any]]:
        """Fetch all documents in review_queue with pending or in_review status."""
        with self.db.get_connection() as conn:
            rows = conn.execute(
                """
                SELECT review_id, document_id, reason, status, created_at
                FROM review_queue
                WHERE status IN ('pending', 'in_review')
                ORDER BY created_at ASC;
                """
            ).fetchall()
            return [
                {
                    "review_id": r[0],
                    "document_id": r[1],
                    "reason": r[2],
                    "status": r[3],
                    "created_at": str(r[4]),
                }
                for r in rows
            ]

    def get_latest_canonical_version(self, document_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve the latest canonical version record for a document."""
        with self.db.get_connection() as conn:
            row = conn.execute(
                """
                SELECT version_id, version_number, source, canonical_payload_json, created_at, reviewer
                FROM canonical_versions
                WHERE document_id = ?
                ORDER BY version_number DESC
                LIMIT 1;
                """,
                [document_id],
            ).fetchone()
            if not row:
                return None
            return {
                "version_id": row[0],
                "version_number": row[1],
                "source": row[2],
                "canonical_payload_json": row[3],
                "created_at": str(row[4]),
                "reviewer": row[5],
            }

    def apply_correction(
        self,
        document_id: str,
        field_path: str,
        new_value: Any,
        reviewer: str = "human_reviewer",
        reason: str = "manual_correction",
    ) -> CorrectionRecord:
        """Apply versioned human correction to canonical envelope with strict Pydantic rehydration and validation."""
        with self.db.get_connection() as conn:
            conn.execute("BEGIN TRANSACTION;")
            try:
                # 1. Fetch current canonical envelope and candidates JSON
                row = conn.execute(
                    """
                    SELECT canonical_payload_json, field_candidates_json, document_family, source_format
                    FROM business_documents
                    WHERE document_id = ?;
                    """,
                    [document_id],
                ).fetchone()

                if not row:
                    raise ValueError(f"Document ID '{document_id}' not found in business_documents.")

                payload_json, candidates_json, family_str, format_str = row[0], row[1], row[2], row[3]

                # Fetch latest canonical version ID
                parent_ver_row = conn.execute(
                    "SELECT version_id, version_number FROM canonical_versions WHERE document_id = ? ORDER BY version_number DESC LIMIT 1;",
                    [document_id],
                ).fetchone()
                parent_ver_id = parent_ver_row[0] if parent_ver_row else None
                prev_ver_num = parent_ver_row[1] if parent_ver_row else 0
                new_ver_num = prev_ver_num + 1

                # 2. Rehydrate the current typed envelope, then export a mutable Python payload.
                current_envelope_data = {
                    "document_id": document_id,
                    "document_family": family_str,
                    "source_format": format_str,
                    "payload": json.loads(payload_json),
                }
                if candidates_json:
                    current_envelope_data["field_candidates"] = json.loads(candidates_json)
                current_envelope = BusinessDocumentEnvelope.model_validate(current_envelope_data)
                payload_dict = current_envelope.payload.model_dump(mode="python")

                old_val = None
                try:
                    old_val = get_field_value(payload_dict, field_path)
                except Exception:
                    pass
                old_val_str = str(old_val) if old_val is not None else None

                # 3. Apply field path correction to payload dict
                set_field_value(payload_dict, field_path, new_value)

                # 4. STRICT REQUIREMENT 7: Rehydrate via Pydantic model_validate
                # If new_value has invalid type (e.g. "abc" for Decimal), this raises ValidationError
                envelope_dict = {
                    "document_id": document_id,
                    "document_family": family_str,
                    "source_format": format_str,
                    "payload": payload_dict,
                }
                if candidates_json:
                    envelope_dict["field_candidates"] = json.loads(candidates_json)

                envelope = BusinessDocumentEnvelope.model_validate(envelope_dict)

                # 5. Update field candidate tracking
                if field_path in envelope.field_candidates:
                    cand = envelope.field_candidates[field_path]
                    cand.value = get_field_value(envelope.payload, field_path)
                    cand.raw_value = str(new_value)
                    cand.extraction_method = "human_corrected"
                else:
                    envelope.field_candidates[field_path] = FieldCandidate(
                        value=get_field_value(envelope.payload, field_path),
                        raw_value=str(new_value),
                        extraction_method="human_corrected",
                    )

                # 6. Rerun validator & completeness
                validation_res = self.validator.validate(envelope)
                comp = self.mapper.evaluate_completeness(envelope)

                new_comp_score = comp.completeness_score
                new_payload_json = envelope.payload.model_dump_json()

                # 7. Create new canonical_versions entry
                new_ver_id = f"ver_{document_id}_{new_ver_num}"
                conn.execute(
                    """
                    INSERT INTO canonical_versions (version_id, document_id, version_number, source, canonical_payload_json, created_at, reviewer, parent_version_id)
                    VALUES (?, ?, ?, 'human_corrected', ?, CURRENT_TIMESTAMP, ?, ?);
                    """,
                    [new_ver_id, document_id, new_ver_num, new_payload_json, reviewer, parent_ver_id],
                )

                # 8. Record correction history
                corr_id = f"corr_{document_id}_{int(datetime.now().timestamp())}_{new_ver_num}"
                corr = CorrectionRecord(
                    correction_id=corr_id,
                    document_id=document_id,
                    canonical_version_before=parent_ver_id,
                    canonical_version_after=new_ver_id,
                    field_path=field_path,
                    old_value=old_val_str,
                    new_value=str(new_value),
                    reviewer=reviewer,
                    reason=reason,
                )
                conn.execute(
                    """
                    INSERT INTO review_corrections (correction_id, document_id, canonical_version_before, canonical_version_after, field_path, old_value, new_value, reviewer, reason, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP);
                    """,
                    [
                        corr.correction_id,
                        corr.document_id,
                        corr.canonical_version_before,
                        corr.canonical_version_after,
                        corr.field_path,
                        corr.old_value,
                        corr.new_value,
                        corr.reviewer,
                        corr.reason,
                    ],
                )

                # 9. Relational Reprojection
                self.projector.project_and_store(conn, envelope, new_comp_score)

                # 10. Update validation issues & review queue status
                conn.execute("DELETE FROM validation_issues WHERE document_id = ?;", [document_id])
                for idx, issue in enumerate(validation_res.issues):
                    conn.execute(
                        """
                        INSERT INTO validation_issues (issue_id, document_id, code, severity, field_path, message, review_required)
                        VALUES (?, ?, ?, ?, ?, ?, ?);
                        """,
                        [
                            f"{document_id}_v_corr_{idx}",
                            document_id,
                            issue.code,
                            issue.severity.value,
                            issue.field_path,
                            issue.message,
                            issue.review_required,
                        ],
                    )

                new_requires_review = validation_res.requires_review or comp.requires_review
                new_status = "accepted" if validation_res.is_valid and not new_requires_review else "corrected"

                conn.execute(
                    """
                    UPDATE review_queue
                    SET status = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE document_id = ?;
                    """,
                    [new_status, document_id],
                )
                conn.execute(
                    "UPDATE documents SET status = ? WHERE document_id = ?;",
                    ["validated" if new_status == "accepted" else "review_required", document_id],
                )

                conn.execute("COMMIT;")
                return corr

            except Exception:
                conn.execute("ROLLBACK;")
                raise
