"""Unit tests for date parsing engine."""

from __future__ import annotations

from datetime import UTC, datetime

from provenmesh.crawler.date_parser import ParsedDate, parse_date, parse_structured_date
from provenmesh.domain.enums import DateConfidence


class TestISOParsing:
    """Tests for ISO 8601 date parsing (strict confidence)."""

    def test_iso_format(self) -> None:
        result = parse_date("2025-03-15T10:30:00Z")
        assert result is not None
        assert result.confidence == DateConfidence.STRICT
        assert result.value.year == 2025
        assert result.value.month == 3

    def test_iso_with_timezone(self) -> None:
        result = parse_date("2025-06-01T14:00:00+05:30")
        assert result is not None
        assert result.confidence == DateConfidence.STRICT

    def test_iso_date_only(self) -> None:
        result = parse_date("2025-03-15")
        assert result is not None
        assert result.confidence == DateConfidence.STRICT


class TestRelativeParsing:
    """Tests for relative date expressions (heuristic confidence)."""

    def test_hours_ago(self) -> None:
        now = datetime(2025, 6, 1, 12, 0, tzinfo=UTC)
        result = parse_date("3 hours ago", fetch_time=now)
        assert result is not None
        assert result.confidence == DateConfidence.HEURISTIC
        assert result.value.hour == 9

    def test_days_ago(self) -> None:
        now = datetime(2025, 6, 10, 12, 0, tzinfo=UTC)
        result = parse_date("5 days ago", fetch_time=now)
        assert result is not None
        assert result.value.day == 5

    def test_yesterday(self) -> None:
        now = datetime(2025, 6, 10, 12, 0, tzinfo=UTC)
        result = parse_date("yesterday", fetch_time=now)
        assert result is not None
        assert result.value.day == 9


class TestStructuredDate:
    """Tests for structured metadata date parsing."""

    def test_json_ld_date(self) -> None:
        result = parse_structured_date("2025-08-12T00:00:00Z", source="json_ld")
        assert result is not None
        assert result.confidence == DateConfidence.STRICT
        assert result.source == "json_ld"


class TestEdgeCases:
    """Tests for edge cases."""

    def test_empty_string(self) -> None:
        assert parse_date("") is None

    def test_none_like(self) -> None:
        assert parse_date("  ") is None

    def test_garbage(self) -> None:
        result = parse_date("not a date at all xyz123")
        # dateparser might parse this or not; either way should not crash
        assert result is None or isinstance(result, ParsedDate)
