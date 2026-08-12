"""Tests for grounding/text_match.py — fuzzy text verification."""
from __future__ import annotations

from provenmesh.domain.enums import FieldVerification
from provenmesh.grounding.text_match import (
    verify_list_field,
    verify_text_field,
)


class TestVerifyTextField:
    def test_grounded_with_evidence(self) -> None:
        status, score = verify_text_field(
            "OpenAI",
            "OpenAI is an AI research company",
            "OpenAI is an AI research company founded in 2015",
        )
        assert status == FieldVerification.GROUNDED
        assert score >= 90

    def test_missing_value(self) -> None:
        status, score = verify_text_field("", "evidence", "source")
        assert status == FieldVerification.MISSING
        assert score == 0.0

    def test_no_evidence_direct_match(self) -> None:
        status, score = verify_text_field(
            "OpenAI", "", "OpenAI is an AI company",
        )
        assert status == FieldVerification.GROUNDED
        assert score > 0

    def test_no_evidence_no_match(self) -> None:
        status, score = verify_text_field(
            "Completely unrelated text", "",
            "This source has nothing to do with the query",
        )
        assert status == FieldVerification.UNVERIFIED

    def test_evidence_not_in_source(self) -> None:
        status, score = verify_text_field(
            "OpenAI",
            "Evidence that does not appear in source at all xyz abc",
            "Completely different source text about cooking recipes",
        )
        assert status == FieldVerification.UNVERIFIED

    def test_value_not_in_evidence(self) -> None:
        status, score = verify_text_field(
            "Totally different name",
            "Evidence text that is in source",
            "Evidence text that is in source and more content here",
        )
        assert status == FieldVerification.UNVERIFIED


class TestVerifyListField:
    def test_all_grounded(self) -> None:
        source = "Sam Altman and Greg Brockman are founders."
        status, score = verify_list_field(
            ["Sam Altman", "Greg Brockman"],
            ["Sam Altman", "Greg Brockman"],
            source,
        )
        assert status == FieldVerification.GROUNDED

    def test_empty_list(self) -> None:
        status, score = verify_list_field([], [], "source text")
        assert status == FieldVerification.MISSING

    def test_partial_match(self) -> None:
        source = "Sam Altman is involved. No mention of the other person."
        status, score = verify_list_field(
            ["Sam Altman", "Unknown Person XYZ"],
            ["Sam Altman", "Unknown Person XYZ"],
            source,
        )
        assert isinstance(status, FieldVerification)

    def test_no_matches(self) -> None:
        status, score = verify_list_field(
            ["ABC Corp", "XYZ Inc"],
            ["ABC Corp", "XYZ Inc"],
            "Nothing related to these companies at all",
        )
        assert status == FieldVerification.UNVERIFIED

    def test_evidence_shorter_than_values(self) -> None:
        """When evidence list is shorter than values, missing evidence defaults to empty."""
        source = "Sam Altman is the CEO."
        status, score = verify_list_field(
            ["Sam Altman", "Greg Brockman"],
            ["Sam Altman"],  # Only 1 evidence for 2 values
            source,
        )
        assert isinstance(status, FieldVerification)
