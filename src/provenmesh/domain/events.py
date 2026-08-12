"""Domain events — internal event bus messages for stage-to-stage communication.

These events decouple pipeline stages so any stage can be scaled,
restarted, or replaced independently (PDF §2 architecture principle).
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class BaseEvent(BaseModel):
    """Base event with correlation tracking."""

    event_id: str = ""
    correlation_id: str = ""
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    source_worker: str = ""


class UrlDiscoveredEvent(BaseEvent):
    """A producer discovered a new detail-page URL to crawl."""

    url: str
    source_name: str
    record_type: str
    listing_page: int = 0
    priority: int = 0


class FetchCompletedEvent(BaseEvent):
    """A crawler worker successfully fetched a page."""

    url: str
    source_name: str
    record_type: str
    content_hash: str
    raw_s3_key: str
    status_code: int
    fetch_tier: int
    content_length: int = 0
    is_duplicate: bool = False


class ExtractionCompletedEvent(BaseEvent):
    """The LLM orchestrator extracted structured data from a page."""

    url: str
    record_type: str
    content_hash: str
    entity_data: dict = Field(default_factory=dict)
    relationship_candidates: list[dict] = Field(default_factory=list)
    provider_used: str = ""
    tokens_used: int = 0
    cost_usd: float = 0.0
    grounding_passed: bool = False
    verification_status: str = "unverified"


class ResolutionCompletedEvent(BaseEvent):
    """The entity resolver canonicalized an entity."""

    entity_id: str
    canonical_id: str
    record_type: str
    resolution_method: str
    confidence: float = 0.0
    needs_review: bool = False


class ExportCompletedEvent(BaseEvent):
    """Records were exported to Google Sheets."""

    export_run_id: str
    tab_name: str
    records_exported: int = 0
    records_skipped: int = 0
    records_failed: int = 0


class ProcessingFailedEvent(BaseEvent):
    """A processing stage failed for an item."""

    url: str = ""
    entity_id: str = ""
    stage: str = ""
    error_type: str = ""
    error_message: str = ""
    attempt_number: int = 0
    max_attempts: int = 5
    will_retry: bool = False
    routed_to_dlq: bool = False
