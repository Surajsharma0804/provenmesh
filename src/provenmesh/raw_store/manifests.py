"""Raw store manifests — crawl run tracking."""

from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel, Field


class CrawlRunManifest(BaseModel):
    """Tracks a complete crawl run for a source."""

    run_id: str = ""
    source_name: str = ""
    vertical: str = ""
    started_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    completed_at: datetime | None = None
    urls_discovered: int = 0
    urls_fetched: int = 0
    urls_failed: int = 0
    urls_deduplicated: int = 0
    bytes_stored: int = 0
    status: str = "running"  # running, completed, failed
