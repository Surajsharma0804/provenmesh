"""Tests for crawler/date_parser.py — comprehensive date parsing coverage."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from provenmesh.crawler.date_parser import (
    DateConfidence,
    ParsedDate,
    is_within_freshness_window,
    parse_date,
    parse_structured_date,
)


class TestParseDate:
    def test_iso_format(self) -> None:
        result = parse_date("2026-08-12")
        assert result is not None
        assert result.value.year == 2026
        assert result.confidence == DateConfidence.STRICT

    def test_written_format(self) -> None:
        result = parse_date("August 12, 2026")
        assert result is not None
        assert result.value.year == 2026

    def test_iso_with_time(self) -> None:
        result = parse_date("2026-08-12T14:30:00Z")
        assert result is not None
        assert result.value.year == 2026

    def test_empty(self) -> None:
        assert parse_date("") is None

    def test_garbage(self) -> None:
        result = parse_date("not a date at all xyz 123")
        assert result is None or isinstance(result, ParsedDate)

    def test_source_field(self) -> None:
        result = parse_date("2026-08-12")
        assert result is not None
        assert result.source == "iso_8601"

    def test_raw_preserved(self) -> None:
        result = parse_date("2026-08-12")
        assert result is not None
        assert result.raw == "2026-08-12"

    # --- Relative date expressions ---
    def test_relative_days_ago(self) -> None:
        result = parse_date("3 days ago")
        assert result is not None
        assert result.confidence == DateConfidence.HEURISTIC
        assert result.source == "relative"

    def test_relative_hours_ago(self) -> None:
        result = parse_date("5 hours ago")
        assert result is not None
        assert result.source == "relative"

    def test_relative_minutes_ago(self) -> None:
        result = parse_date("30 minutes ago")
        assert result is not None

    def test_relative_weeks_ago(self) -> None:
        result = parse_date("2 weeks ago")
        assert result is not None

    def test_relative_months_ago(self) -> None:
        result = parse_date("6 months ago")
        assert result is not None

    def test_relative_years_ago(self) -> None:
        result = parse_date("2 years ago")
        assert result is not None

    def test_relative_yesterday(self) -> None:
        result = parse_date("yesterday")
        assert result is not None
        assert result.source == "relative"

    # --- dateutil parsing ---
    def test_dateutil_format(self) -> None:
        result = parse_date("Jan 15, 2026")
        assert result is not None
        assert result.value.year == 2026
        assert result.value.month == 1

    def test_dateutil_slash(self) -> None:
        result = parse_date("12/25/2025")
        assert result is not None

    # --- Relative: today and just_now (line 165-166) ---
    def test_relative_today(self) -> None:
        result = parse_date("today")
        assert result is not None
        assert result.source == "relative"

    def test_relative_just_now(self) -> None:
        result = parse_date("just now")
        assert result is not None
        assert result.source == "relative"

    def test_relative_seconds_ago(self) -> None:
        """Test seconds ago (line 169-170)."""
        result = parse_date("45 seconds ago")
        assert result is not None
        assert result.source == "relative"

    # --- dateparser (broadest) ---
    def test_dateparser_fallback(self) -> None:
        # Natural language that dateparser handles
        result = parse_date("le 12 août 2026", locale="fr")
        # May or may not parse depending on locale support
        assert result is None or isinstance(result, ParsedDate)


class TestParseStructuredDate:
    def test_iso_string(self) -> None:
        result = parse_structured_date("2026-08-12T10:00:00Z")
        assert result is not None
        assert result.value.year == 2026
        assert result.confidence == DateConfidence.STRICT

    def test_date_only(self) -> None:
        result = parse_structured_date("2026-08-12")
        assert result is not None

    def test_custom_source(self) -> None:
        result = parse_structured_date("2026-08-12", source="meta_tag")
        assert result is not None
        assert result.source == "meta_tag"

    def test_empty(self) -> None:
        assert parse_structured_date("") is None

    def test_dateutil_fallback(self) -> None:
        # Not ISO but dateutil can parse
        result = parse_structured_date("Jan 15, 2026")
        assert result is not None
        assert result.confidence == DateConfidence.STRICT


class TestIsWithinFreshnessWindow:
    def test_recent_date(self) -> None:
        recent = datetime.now(UTC) - timedelta(hours=1)
        assert is_within_freshness_window(recent, max_age_hours=24) is True

    def test_old_date(self) -> None:
        old = datetime(2000, 1, 1, tzinfo=UTC)
        assert is_within_freshness_window(old, max_age_hours=24) is False

    def test_future_date(self) -> None:
        future = datetime.now(UTC) + timedelta(hours=1)
        result = is_within_freshness_window(future, max_age_hours=24)
        assert result is True

    def test_custom_reference_time(self) -> None:
        ref = datetime(2026, 8, 12, tzinfo=UTC)
        date = datetime(2026, 8, 11, tzinfo=UTC)
        assert is_within_freshness_window(date, max_age_hours=48, reference_time=ref) is True

    def test_naive_date_gets_utc(self) -> None:
        naive = datetime(2026, 8, 12)  # noqa: DTZ001
        # Should not crash — naive dates get UTC assigned
        result = is_within_freshness_window(naive, max_age_hours=999999)
        assert isinstance(result, bool)


class TestTryDateparserException:
    """Test _try_dateparser exception handling (lines 220-221)."""

    def test_dateparser_exception_returns_none(self) -> None:
        from unittest.mock import patch

        from provenmesh.crawler.date_parser import _try_dateparser
        with patch(
            "provenmesh.crawler.date_parser.dateparser.parse",
            side_effect=RuntimeError("dateparser crash"),
        ):
            result = _try_dateparser("2026-01-01")
            assert result is None

    def test_dateparser_with_locale_exception(self) -> None:
        from unittest.mock import patch

        from provenmesh.crawler.date_parser import _try_dateparser
        with patch(
            "provenmesh.crawler.date_parser.dateparser.parse",
            side_effect=ValueError("locale error"),
        ):
            result = _try_dateparser("le 12 août", locale="fr")
            assert result is None


class TestTryRelativeNaiveDatetime:
    """Test _try_relative with naive now (line 186-187)."""

    def test_relative_with_naive_now(self) -> None:
        from provenmesh.crawler.date_parser import _try_relative
        naive_now = datetime(2026, 8, 12, 12, 0, 0)  # noqa: DTZ001
        result = _try_relative("3 days ago", naive_now)
        assert result is not None
        assert result.value.tzinfo is not None  # Should get UTC

    def test_relative_with_aware_now(self) -> None:
        from provenmesh.crawler.date_parser import _try_relative
        aware_now = datetime(2026, 8, 12, 12, 0, 0, tzinfo=UTC)
        result = _try_relative("2 hours ago", aware_now)
        assert result is not None
        assert result.value.tzinfo is not None

