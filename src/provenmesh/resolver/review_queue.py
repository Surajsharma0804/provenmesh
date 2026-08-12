"""Human review queue — uncertain matches routed for manual decision (PDF §6.3).

Entities with embedding similarity in the [0.75, 0.88) band are
uncertain — too similar to ignore, too different to auto-merge.
These are queued for human review.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field

from provenmesh.domain.enums import ReviewStatus
from provenmesh.observability.logging import get_logger

logger = get_logger(__name__)


class ReviewItem(BaseModel):
    """An entity match pending human review."""

    review_id: str = ""
    extracted_name: str = ""
    candidate_canonical_id: str = ""
    candidate_name: str = ""
    record_type: str = ""
    similarity_score: float = 0.0
    resolution_method: str = ""
    evidence_summary: str = ""
    source_url: str = ""
    status: ReviewStatus = ReviewStatus.NEEDS_REVIEW
    reviewer: str = ""
    decision: str = ""  # "merge", "new_entity", "reject"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    resolved_at: datetime | None = None


class ReviewQueue:
    """In-memory review queue (can be backed by DB for persistence).

    In production, this would be a database-backed queue with a
    review UI. For v1.0, we store in-memory and log for manual review.
    """

    def __init__(self) -> None:
        self._items: list[ReviewItem] = []
        self._resolved: list[ReviewItem] = []

    def add(self, item: ReviewItem) -> None:
        """Add an item to the review queue."""
        self._items.append(item)
        logger.info(
            "review_item_added",
            extracted_name=item.extracted_name,
            candidate=item.candidate_name,
            score=round(item.similarity_score, 3),
            method=item.resolution_method,
        )

    def get_pending(self, record_type: str | None = None) -> list[ReviewItem]:
        """Get all pending review items, optionally filtered by type."""
        items = [i for i in self._items if i.status == ReviewStatus.NEEDS_REVIEW]
        if record_type:
            items = [i for i in items if i.record_type == record_type]
        return items

    def resolve_item(
        self,
        review_id: str,
        decision: str,
        reviewer: str = "system",
    ) -> ReviewItem | None:
        """Resolve a review item with a decision."""
        for item in self._items:
            if item.review_id == review_id:
                item.status = ReviewStatus.RESOLVED
                item.decision = decision
                item.reviewer = reviewer
                item.resolved_at = datetime.now(timezone.utc)
                self._resolved.append(item)
                logger.info(
                    "review_item_resolved",
                    review_id=review_id,
                    decision=decision,
                    reviewer=reviewer,
                )
                return item
        return None

    @property
    def pending_count(self) -> int:
        return sum(1 for i in self._items if i.status == ReviewStatus.NEEDS_REVIEW)

    @property
    def resolved_count(self) -> int:
        return len(self._resolved)

    def get_stats(self) -> dict[str, int]:
        return {
            "pending": self.pending_count,
            "resolved": self.resolved_count,
            "total": len(self._items),
        }
