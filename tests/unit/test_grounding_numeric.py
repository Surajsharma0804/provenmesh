"""Tests for grounding/numeric_match.py — numeric parsing and verification."""
from __future__ import annotations

from provenmesh.domain.enums import FieldVerification
from provenmesh.grounding.numeric_match import (
    extract_all_numbers,
    parse_numeric,
    verify_numeric_field,
)


class TestParseNumeric:
    def test_simple_integer(self) -> None:
        assert parse_numeric("42") == 42.0

    def test_with_commas(self) -> None:
        assert parse_numeric("1,700") == 1700.0

    def test_dollar_amount(self) -> None:
        assert parse_numeric("$6.6B") == 6_600_000_000.0

    def test_billion_word(self) -> None:
        assert parse_numeric("6.6 billion") == 6_600_000_000.0

    def test_million(self) -> None:
        assert parse_numeric("$50M") == 50_000_000.0

    def test_thousand(self) -> None:
        assert parse_numeric("5K") == 5_000.0

    def test_trillion(self) -> None:
        assert parse_numeric("1.5T") == 1_500_000_000_000.0

    def test_empty_string(self) -> None:
        assert parse_numeric("") is None

    def test_non_numeric(self) -> None:
        assert parse_numeric("not a number") is None

    def test_euro(self) -> None:
        result = parse_numeric("€100M")
        assert result == 100_000_000.0

    def test_plain_float(self) -> None:
        assert parse_numeric("3.14") == 3.14

    def test_bn_suffix(self) -> None:
        assert parse_numeric("$80bn") == 80_000_000_000.0


class TestExtractAllNumbers:
    def test_multiple_numbers(self) -> None:
        text = "Revenue was $6.6B and they have 1,700 employees"
        numbers = extract_all_numbers(text)
        assert len(numbers) >= 2
        assert 6_600_000_000.0 in numbers
        assert 1700.0 in numbers

    def test_no_numbers(self) -> None:
        assert extract_all_numbers("no numbers here") == []

    def test_currency_amounts(self) -> None:
        numbers = extract_all_numbers("$50M funding, $20B valuation")
        assert 50_000_000.0 in numbers
        assert 20_000_000_000.0 in numbers


class TestVerifyNumericField:
    def test_exact_match(self) -> None:
        status, score = verify_numeric_field(
            "$7.3B",
            "raised $7.3 billion in funding",
            "Company raised $7.3 billion in funding",
        )
        assert status == FieldVerification.GROUNDED
        assert score > 0.99

    def test_close_match(self) -> None:
        status, score = verify_numeric_field(
            "$7.3B",
            "raised approximately $7.3 billion",
            "Approximately $7.3 billion raised",
        )
        assert status == FieldVerification.GROUNDED

    def test_no_match(self) -> None:
        status, score = verify_numeric_field(
            "$7.3B",
            "no numbers here at all",
            "no numbers here either",
        )
        assert status == FieldVerification.UNVERIFIED

    def test_missing_value(self) -> None:
        status, score = verify_numeric_field(
            "", "evidence", "source",
        )
        assert status == FieldVerification.MISSING

    def test_non_parseable(self) -> None:
        status, score = verify_numeric_field(
            "not a number", "evidence", "source",
        )
        assert status == FieldVerification.MISSING

    def test_evidence_match_only(self) -> None:
        status, score = verify_numeric_field(
            "$50M",
            "They raised $50 million",
            "No numbers in source",
        )
        assert status == FieldVerification.GROUNDED

    def test_source_number_is_zero(self) -> None:
        """Zero source numbers should be skipped (line 112-113)."""
        status, score = verify_numeric_field(
            "$50M",
            "They have 0 revenue but raised $50M",
            "They have 0 revenue but raised $50M",
        )
        assert status == FieldVerification.GROUNDED


class TestParseNumericEdgeCases:
    def test_invalid_number_str_in_match(self) -> None:
        """When regex matches but float() fails (lines 71-72)."""
        # This is hard to trigger directly since regex validates digits
        # But let's test edge cases
        assert parse_numeric("$") is None
        assert parse_numeric(",.") is None

    def test_suffix_only(self) -> None:
        """Just a suffix character."""
        assert parse_numeric("B") is None
        assert parse_numeric("M") is None

    def test_float_parse_via_regex_valueerror(self) -> None:
        """Mock NUMERIC_PATTERN to return a match with invalid number (71-72)."""
        from unittest.mock import MagicMock, patch

        import provenmesh.grounding.numeric_match as nm

        mock_match = MagicMock()
        mock_match.group.side_effect = lambda x: {1: "not_a_float", 2: "M"}[x]

        mock_pattern = MagicMock()
        mock_pattern.search.return_value = mock_match

        with patch.object(nm, "NUMERIC_PATTERN", mock_pattern):
            result = nm.parse_numeric("fake input")
            assert result is None

    def test_extract_all_numbers_valueerror(self) -> None:
        """Mock NUMERIC_PATTERN finditer to return invalid match (133-134)."""
        from unittest.mock import MagicMock, patch

        import provenmesh.grounding.numeric_match as nm

        mock_match = MagicMock()
        mock_match.group.side_effect = lambda x: {1: "invalid", 2: ""}[x]

        mock_pattern = MagicMock()
        mock_pattern.finditer.return_value = [mock_match]

        with patch.object(nm, "NUMERIC_PATTERN", mock_pattern):
            result = nm.extract_all_numbers("fake text")
            assert result == []
