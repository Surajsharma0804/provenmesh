"""Tests for raw_store/manifests.py — CrawlRunManifest model."""
from __future__ import annotations

from provenmesh.raw_store.manifests import CrawlRunManifest


class TestCrawlRunManifest:
    def test_defaults(self) -> None:
        m = CrawlRunManifest()
        assert m.run_id == ""
        assert m.source_name == ""
        assert m.vertical == ""
        assert m.urls_discovered == 0
        assert m.urls_fetched == 0
        assert m.urls_failed == 0
        assert m.urls_deduplicated == 0
        assert m.bytes_stored == 0
        assert m.status == "running"
        assert m.completed_at is None
        assert m.started_at is not None

    def test_custom_values(self) -> None:
        m = CrawlRunManifest(
            run_id="run-123",
            source_name="crunchbase",
            vertical="startups",
            urls_discovered=100,
            urls_fetched=95,
            urls_failed=5,
            status="completed",
        )
        assert m.run_id == "run-123"
        assert m.source_name == "crunchbase"
        assert m.urls_discovered == 100
        assert m.status == "completed"
