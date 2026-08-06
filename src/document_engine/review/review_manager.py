"""Review queue lifecycle and human correction manager."""

from datetime import datetime, timezone
import json
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from document_engine.core.models import ReviewStatus
from document_engine.storage.database import DuckDBStorage


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


class CorrectionRecord(BaseModel):
    correction_id: str
    document_id: str
    field_path: str
    old_value: Optional[str] = None
    new_value: str
    reviewer: str = "human_reviewer"
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


class ReviewManager:
    def __init__(self, db_storage: DuckDBStorage):
        self.db = db_storage

    def list_pending_reviews(self) -> List[Dict[str, Any]]:
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

    def apply_correction(
        self,
        document_id: str,
        field_path: str,
        new_value: str,
        reviewer: str = "human_reviewer",
    ) -> CorrectionRecord:
        with self.db.get_connection() as conn:
            conn.execute("BEGIN TRANSACTION;")
            try:
                # Fetch current canonical payload
                res = conn.execute(
                    "SELECT canonical_payload_json FROM business_documents WHERE document_id = ?;",
                    [document_id],
                ).fetchone()

                old_val_str = None
                if res and res[0]:
                    payload_dict = json.loads(res[0])
                    # Get old value if present
                    old_val_str = str(payload_dict.get(field_path, ""))

                    # Update dict at field path
                    payload_dict[field_path] = new_value
                    updated_json = json.dumps(payload_dict, ensure_ascii=False)

                    conn.execute(
                        "UPDATE business_documents SET canonical_payload_json = ? WHERE document_id = ?;",
                        [updated_json, document_id],
                    )

                corr_id = f"corr_{document_id}_{int(datetime.now().timestamp())}"
                corr = CorrectionRecord(
                    correction_id=corr_id,
                    document_id=document_id,
                    field_path=field_path,
                    old_value=old_val_str,
                    new_value=new_value,
                    reviewer=reviewer,
                )

                conn.execute(
                    """
                    INSERT INTO review_corrections (correction_id, document_id, field_path, old_value, new_value, reviewer, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP);
                    """,
                    [
                        corr.correction_id,
                        corr.document_id,
                        corr.field_path,
                        corr.old_value,
                        corr.new_value,
                        corr.reviewer,
                    ],
                )

                # Update review queue status
                conn.execute(
                    """
                    UPDATE review_queue
                    SET status = 'corrected', updated_at = CURRENT_TIMESTAMP
                    WHERE document_id = ?;
                    """,
                    [document_id],
                )

                conn.execute("COMMIT;")
                return corr

            except Exception as e:
                conn.execute("ROLLBACK;")
                raise e
