"""Tests for observability/logging.py — JSONFormatter and structured logging."""
from __future__ import annotations

import json
import logging
from pathlib import Path

from provenmesh.observability.logging import (
    JSONFormatter,
    add_correlation_id,
    add_service_info,
    get_correlation_id,
    new_correlation_id,
    set_correlation_id,
    setup_logging,
)


class TestCorrelationId:
    def test_get_generates_if_empty(self) -> None:
        set_correlation_id("")
        cid = get_correlation_id()
        assert len(cid) == 36  # UUID format

    def test_set_and_get(self) -> None:
        set_correlation_id("test-123")
        assert get_correlation_id() == "test-123"

    def test_new_correlation_id(self) -> None:
        cid = new_correlation_id()
        assert len(cid) == 36
        assert get_correlation_id() == cid

    def test_new_overwrites_old(self) -> None:
        set_correlation_id("old")
        cid = new_correlation_id()
        assert cid != "old"
        assert get_correlation_id() == cid


class TestJSONFormatter:
    def test_basic_format(self) -> None:
        formatter = JSONFormatter()
        record = logging.LogRecord(
            name="test.logger",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="Hello world",
            args=(),
            exc_info=None,
        )
        output = formatter.format(record)
        parsed = json.loads(output)
        assert parsed["level"] == "INFO"
        assert parsed["logger"] == "test.logger"
        assert parsed["message"] == "Hello world"
        assert "correlation_id" in parsed
        assert "timestamp" in parsed

    def test_with_event_attr(self) -> None:
        formatter = JSONFormatter()
        record = logging.LogRecord(
            name="test", level=logging.INFO,
            pathname="", lineno=0, msg="msg", args=(), exc_info=None,
        )
        record.event = "custom_event"  # type: ignore[attr-defined]
        output = formatter.format(record)
        parsed = json.loads(output)
        assert parsed["event"] == "custom_event"

    def test_with_exception(self) -> None:
        formatter = JSONFormatter()
        try:
            raise ValueError("test error")
        except ValueError:
            import sys
            exc_info = sys.exc_info()

        record = logging.LogRecord(
            name="test", level=logging.ERROR,
            pathname="", lineno=0, msg="failed",
            args=(), exc_info=exc_info,
        )
        output = formatter.format(record)
        parsed = json.loads(output)
        assert parsed["exception"]["type"] == "ValueError"
        assert "test error" in parsed["exception"]["message"]

    def test_with_extra_attrs(self) -> None:
        formatter = JSONFormatter()
        record = logging.LogRecord(
            name="test", level=logging.INFO,
            pathname="", lineno=0, msg="fetch",
            args=(), exc_info=None,
        )
        record.url = "https://example.com"  # type: ignore[attr-defined]
        record.latency_ms = 42.5  # type: ignore[attr-defined]
        record.provider = "gemini"  # type: ignore[attr-defined]
        output = formatter.format(record)
        parsed = json.loads(output)
        assert parsed["url"] == "https://example.com"
        assert parsed["latency_ms"] == 42.5
        assert parsed["provider"] == "gemini"

    def test_no_extra_attrs(self) -> None:
        formatter = JSONFormatter()
        record = logging.LogRecord(
            name="test", level=logging.INFO,
            pathname="", lineno=0, msg="plain",
            args=(), exc_info=None,
        )
        output = formatter.format(record)
        parsed = json.loads(output)
        assert "url" not in parsed
        assert "provider" not in parsed


class TestStructlogProcessors:
    def test_add_correlation_id(self) -> None:
        set_correlation_id("proc-test")
        event_dict: dict = {"event": "test"}
        result = add_correlation_id(None, "", event_dict)
        assert result["correlation_id"] == "proc-test"

    def test_add_service_info(self) -> None:
        event_dict: dict = {"event": "test"}
        result = add_service_info(None, "", event_dict)
        assert result["service"] == "provenmesh"

    def test_add_service_info_no_override(self) -> None:
        event_dict: dict = {"event": "test", "service": "custom"}
        result = add_service_info(None, "", event_dict)
        assert result["service"] == "custom"


class TestSetupLogging:
    def test_default_config(self) -> None:
        setup_logging(config_path=None)

    def test_nonexistent_config(self) -> None:
        setup_logging(config_path=Path("/nonexistent/config.yaml"))

    def test_yaml_config_file(self, tmp_path: Path) -> None:
        """Test loading from a real YAML config file (lines 107-109)."""
        config = {
            "version": 1,
            "disable_existing_loggers": False,
            "handlers": {
                "console": {
                    "class": "logging.StreamHandler",
                    "level": "DEBUG",
                },
            },
            "root": {
                "level": "DEBUG",
                "handlers": ["console"],
            },
        }
        import yaml
        config_file = tmp_path / "logging.yaml"
        config_file.write_text(yaml.dump(config))
        setup_logging(config_path=config_file)

