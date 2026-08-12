"""Tests for domain/events.py — all domain event models."""
from __future__ import annotations

from provenmesh.domain.events import (
    BaseEvent,
    ExportCompletedEvent,
    ExtractionCompletedEvent,
    FetchCompletedEvent,
    ProcessingFailedEvent,
    ResolutionCompletedEvent,
    UrlDiscoveredEvent,
)


class TestBaseEvent:
    def test_defaults(self) -> None:
        event = BaseEvent()
        assert event.event_id == ""
        assert event.correlation_id == ""
        assert event.source_worker == ""
        assert event.timestamp is not None


class TestUrlDiscoveredEvent:
    def test_creation(self) -> None:
        event = UrlDiscoveredEvent(
            url="https://example.com",
            source_name="crunchbase",
            record_type="STARTUP",
            listing_page=1,
            priority=5,
        )
        assert event.url == "https://example.com"
        assert event.source_name == "crunchbase"
        assert event.record_type == "STARTUP"
        assert event.listing_page == 1
        assert event.priority == 5


class TestFetchCompletedEvent:
    def test_creation(self) -> None:
        event = FetchCompletedEvent(
            url="https://example.com",
            source_name="crunchbase",
            record_type="STARTUP",
            content_hash="abc123",
            raw_s3_key="raw/crunchbase/2026/08/12/abc123/payload.html",
            status_code=200,
            fetch_tier=1,
            content_length=5000,
            is_duplicate=False,
        )
        assert event.status_code == 200
        assert event.fetch_tier == 1
        assert event.is_duplicate is False


class TestExtractionCompletedEvent:
    def test_creation(self) -> None:
        event = ExtractionCompletedEvent(
            url="https://example.com",
            record_type="STARTUP",
            content_hash="abc123",
            entity_data={"entityName": {"value": "TestCo"}},
            provider_used="gemini",
            tokens_used=1000,
            cost_usd=0.01,
            grounding_passed=True,
            verification_status="grounded",
        )
        assert event.provider_used == "gemini"
        assert event.grounding_passed is True

    def test_defaults(self) -> None:
        event = ExtractionCompletedEvent(
            url="u", record_type="STARTUP", content_hash="h",
        )
        assert event.entity_data == {}
        assert event.relationship_candidates == []
        assert event.tokens_used == 0


class TestResolutionCompletedEvent:
    def test_creation(self) -> None:
        event = ResolutionCompletedEvent(
            entity_id="e1",
            canonical_id="startup_openai",
            record_type="STARTUP",
            resolution_method="exact",
            confidence=0.99,
            needs_review=False,
        )
        assert event.canonical_id == "startup_openai"
        assert event.resolution_method == "exact"


class TestExportCompletedEvent:
    def test_creation(self) -> None:
        event = ExportCompletedEvent(
            export_run_id="run1",
            tab_name="Startups",
            records_exported=50,
            records_skipped=2,
            records_failed=1,
        )
        assert event.records_exported == 50
        assert event.records_failed == 1


class TestProcessingFailedEvent:
    def test_creation(self) -> None:
        event = ProcessingFailedEvent(
            url="https://example.com",
            stage="extraction",
            error_type="ValueError",
            error_message="bad input",
            attempt_number=3,
            max_attempts=5,
            will_retry=True,
            routed_to_dlq=False,
        )
        assert event.stage == "extraction"
        assert event.will_retry is True
        assert event.routed_to_dlq is False

    def test_defaults(self) -> None:
        event = ProcessingFailedEvent()
        assert event.url == ""
        assert event.entity_id == ""
        assert event.attempt_number == 0
