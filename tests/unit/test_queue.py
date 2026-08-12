"""Unit tests for queue messages."""

from __future__ import annotations

from provenmesh.queue.messages import (
    CrawlMessage,
    DLQMessage,
    ExtractionMessage,
    QueueMessage,
)


class TestQueueMessage:
    """Tests for message serialization."""

    def test_serialize_deserialize(self) -> None:
        msg = CrawlMessage(
            url="https://example.com",
            source_name="test_source",
            record_type="STARTUP",
            correlation_id="test-123",
        )
        stream_data = msg.to_stream_data()
        assert "data" in stream_data

        restored = CrawlMessage.from_stream_data(stream_data)
        assert restored.url == "https://example.com"
        assert restored.source_name == "test_source"
        assert restored.correlation_id == "test-123"

    def test_dlq_from_failed_message(self) -> None:
        original = CrawlMessage(
            url="https://example.com",
            correlation_id="test-456",
            attempt=3,
        )
        dlq = DLQMessage.from_failed_message(
            original=original,
            stage="crawl",
            error=RuntimeError("test error"),
            original_stream="provenmesh:discovery",
        )
        assert dlq.stage == "crawl"
        assert dlq.error_type == "RuntimeError"
        assert dlq.error_message == "test error"
        assert dlq.attempt == 3
