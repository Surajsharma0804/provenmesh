"""Queue message types — serializable payloads for Redis Streams."""

from __future__ import annotations

import json
from datetime import datetime

from pydantic import BaseModel, Field


class QueueMessage(BaseModel):
    """Base message for all queue communications."""

    message_id: str = ""
    correlation_id: str = ""
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    attempt: int = 0
    max_attempts: int = 5
    source_worker: str = ""

    def to_stream_data(self) -> dict[str, str]:
        """Serialize to Redis Streams field-value pairs."""
        return {"data": self.model_dump_json()}

    @classmethod
    def from_stream_data(cls, data: dict[bytes | str, bytes | str]) -> "QueueMessage":
        """Deserialize from Redis Streams field-value pairs."""
        raw = data.get(b"data") or data.get("data", b"{}")
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        return cls.model_validate_json(raw)


class CrawlMessage(QueueMessage):
    """Message requesting a detail page crawl."""

    url: str = ""
    source_name: str = ""
    record_type: str = ""
    listing_page: int = 0
    fetch_tier: int = 1
    priority: int = 0


class ExtractionMessage(QueueMessage):
    """Message requesting LLM extraction from a fetched page."""

    url: str = ""
    source_name: str = ""
    record_type: str = ""
    content_hash: str = ""
    raw_s3_key: str = ""
    content_length: int = 0


class ResolutionMessage(QueueMessage):
    """Message requesting entity resolution."""

    entity_id: str = ""
    record_type: str = ""
    entity_data: str = ""  # JSON-encoded entity
    relationship_candidates: str = ""  # JSON-encoded list


class ExportMessage(QueueMessage):
    """Message requesting export of resolved records."""

    export_run_id: str = ""
    record_type: str = ""
    batch_start: int = 0
    batch_size: int = 500


class DLQMessage(QueueMessage):
    """Dead letter queue entry with failure context (v2 §12)."""

    original_stream: str = ""
    stage: str = ""
    error_type: str = ""
    error_message: str = ""
    original_data: str = ""  # JSON-encoded original message

    @classmethod
    def from_failed_message(
        cls,
        original: QueueMessage,
        stage: str,
        error: Exception,
        original_stream: str,
    ) -> "DLQMessage":
        """Create a DLQ entry from a failed message."""
        return cls(
            correlation_id=original.correlation_id,
            original_stream=original_stream,
            stage=stage,
            error_type=type(error).__name__,
            error_message=str(error)[:1000],  # Truncate long error messages
            original_data=original.model_dump_json(),
            attempt=original.attempt,
            max_attempts=original.max_attempts,
        )
