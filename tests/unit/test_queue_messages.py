"""Tests for queue/messages.py — queue message serialization."""
from __future__ import annotations

from provenmesh.queue.messages import (
    CrawlMessage,
    DLQMessage,
    ExportMessage,
    ExtractionMessage,
    QueueMessage,
    ResolutionMessage,
)


class TestQueueMessage:
    def test_defaults(self) -> None:
        m = QueueMessage()
        assert m.message_id == ""
        assert m.correlation_id == ""
        assert m.attempt == 0
        assert m.max_attempts == 5

    def test_to_stream_data(self) -> None:
        m = QueueMessage(message_id="msg1", correlation_id="cid1")
        data = m.to_stream_data()
        assert "data" in data
        assert "msg1" in data["data"]

    def test_from_stream_data(self) -> None:
        m = QueueMessage(message_id="msg1", correlation_id="cid1")
        stream_data = m.to_stream_data()
        restored = QueueMessage.from_stream_data(stream_data)
        assert restored.message_id == "msg1"
        assert restored.correlation_id == "cid1"

    def test_from_stream_data_bytes(self) -> None:
        m = QueueMessage(message_id="msg2")
        stream_data = m.to_stream_data()
        bytes_data = {b"data": stream_data["data"].encode("utf-8")}
        restored = QueueMessage.from_stream_data(bytes_data)
        assert restored.message_id == "msg2"


class TestCrawlMessage:
    def test_creation(self) -> None:
        m = CrawlMessage(
            url="https://example.com",
            source_name="crunchbase",
            record_type="STARTUP",
            listing_page=1,
            fetch_tier=1,
        )
        assert m.url == "https://example.com"
        assert m.source_name == "crunchbase"

    def test_serialization_roundtrip(self) -> None:
        m = CrawlMessage(url="https://test.com", record_type="PRODUCT")
        data = m.to_stream_data()
        restored = CrawlMessage.from_stream_data(data)
        assert restored.url == "https://test.com"
        assert restored.record_type == "PRODUCT"


class TestExtractionMessage:
    def test_creation(self) -> None:
        m = ExtractionMessage(
            url="https://example.com", content_hash="hash1",
            raw_s3_key="raw/key", record_type="STARTUP",
        )
        assert m.content_hash == "hash1"


class TestResolutionMessage:
    def test_creation(self) -> None:
        m = ResolutionMessage(
            entity_id="e1", record_type="STARTUP", entity_data="{}",
        )
        assert m.entity_id == "e1"


class TestExportMessage:
    def test_creation(self) -> None:
        m = ExportMessage(
            export_run_id="run1", record_type="STARTUP",
            batch_start=0, batch_size=500,
        )
        assert m.batch_size == 500


class TestDLQMessage:
    def test_from_failed_message(self) -> None:
        original = CrawlMessage(
            url="https://fail.com",
            record_type="STARTUP",
            correlation_id="cid-fail",
        )
        dlq = DLQMessage.from_failed_message(
            original=original,
            stage="crawl",
            error=ValueError("test error"),
            original_stream="provenmesh:discovery",
        )
        assert dlq.stage == "crawl"
        assert dlq.error_type == "ValueError"
        assert "test error" in dlq.error_message
        assert dlq.correlation_id == "cid-fail"
        assert dlq.original_stream == "provenmesh:discovery"

    def test_error_truncation(self) -> None:
        original = QueueMessage()
        long_error = ValueError("x" * 2000)
        dlq = DLQMessage.from_failed_message(
            original=original, stage="test",
            error=long_error, original_stream="s",
        )
        assert len(dlq.error_message) <= 1000
