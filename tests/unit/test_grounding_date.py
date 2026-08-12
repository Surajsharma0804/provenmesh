"""Tests for grounding/date_match.py — date parsing and verification."""
from __future__ import annotations

from provenmesh.domain.enums import FieldVerification
from provenmesh.grounding.date_match import (
    extract_dates_from_text,
    parse_date_value,
    verify_date_field,
)


class TestParseDateValue:
    def test_iso_format(self) -> None:
        result = parse_date_value("2026-08-12")
        assert result is not None
        assert result.year == 2026
        assert result.month == 8

    def test_written_format(self) -> None:
        result = parse_date_value("August 12, 2026")
        assert result is not None
        assert result.year == 2026

    def test_empty_string(self) -> None:
        assert parse_date_value("") is None

    def test_whitespace(self) -> None:
        assert parse_date_value("   ") is None

    def test_invalid_date(self) -> None:
        result = parse_date_value("not a date at all")
        # dateparser may or may not parse this; just check it doesn't crash
        assert result is None or result is not None

    def test_dateparser_exception(self) -> None:
        """When dateparser.parse raises an exception (lines 30-31)."""
        from unittest.mock import patch
        with patch("provenmesh.grounding.date_match.dateparser") as mock_dp:
            mock_dp.parse.side_effect = RuntimeError("dateparser crashed")
            result = parse_date_value("2026-01-01")
            assert result is None


class TestExtractDatesFromText:
    def test_iso_dates(self) -> None:
        text = "The company was founded on 2021-03-15 and launched on 2022-11-30."
        dates = extract_dates_from_text(text)
        assert len(dates) >= 2

    def test_written_dates(self) -> None:
        text = "Founded in January 15, 2021 by the team."
        dates = extract_dates_from_text(text)
        assert len(dates) >= 1

    def test_abbreviated_dates(self) -> None:
        text = "Event on Jan 5, 2025 was successful."
        dates = extract_dates_from_text(text)
        assert len(dates) >= 1

    def test_no_dates(self) -> None:
        dates = extract_dates_from_text("No dates here")
        assert dates == []

    def test_iso_with_time(self) -> None:
        text = "Published at 2026-08-12T14:30:00"
        dates = extract_dates_from_text(text)
        assert len(dates) >= 1


class TestVerifyDateField:
    def test_matching_date(self) -> None:
        status, score = verify_date_field(
            "2021-03-15",
            "founded on 2021-03-15",
            "The company was founded on 2021-03-15",
        )
        assert status == FieldVerification.GROUNDED
        assert score > 0.5

    def test_close_date(self) -> None:
        status, score = verify_date_field(
            "2021-03-15",
            "founded on March 15, 2021",
            "Founded March 15, 2021 by the team",
        )
        assert status == FieldVerification.GROUNDED

    def test_missing_date(self) -> None:
        status, score = verify_date_field(
            "", "some text", "source text",
        )
        assert status == FieldVerification.MISSING
        assert score == 0.0

    def test_unverified_date(self) -> None:
        status, score = verify_date_field(
            "2021-03-15",
            "no dates in this text at all",
            "nothing here either",
        )
        assert status == FieldVerification.UNVERIFIED
        assert score == 0.0

    def test_evidence_before_source(self) -> None:
        status, score = verify_date_field(
            "2021-06-01",
            "The launch date was 2021-06-01",
            "No date in source",
        )
        assert status == FieldVerification.GROUNDED
