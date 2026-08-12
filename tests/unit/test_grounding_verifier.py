"""Tests for grounding/verifier.py — field classification and verification routing."""
from __future__ import annotations

from provenmesh.domain.enums import FieldVerification, VerificationStatus
from provenmesh.grounding.verifier import (
    aggregate_verification,
    classify_field,
    verify_field,
)


class TestClassifyField:
    def test_numeric_fields(self) -> None:
        for field in ["fundingTotal", "employeeCount", "salaryMin", "githubStars"]:
            assert classify_field(field) == "numeric"

    def test_date_fields(self) -> None:
        for field in ["foundedDate", "launchDate", "publishedDate", "postedDate"]:
            assert classify_field(field) == "date"

    def test_url_fields(self) -> None:
        for field in ["website", "githubUrl", "linkedinUrl"]:
            assert classify_field(field) == "url"

    def test_text_fields(self) -> None:
        for field in ["description", "name", "summary", "title"]:
            assert classify_field(field) == "text"


class TestVerifyField:
    def test_text_field(self) -> None:
        status, score = verify_field(
            "description", "AI company", "AI company building models",
            "Anthropic is an AI company building models",
        )
        assert status == FieldVerification.GROUNDED
        assert score > 0

    def test_url_field(self) -> None:
        status, score = verify_field(
            "website", "https://openai.com",
            "Visit https://openai.com for more info",
            "Visit https://openai.com for more info",
        )
        assert status == FieldVerification.GROUNDED

    def test_url_field_missing(self) -> None:
        status, score = verify_field(
            "website", "", "no url here", "no url here",
        )
        assert status == FieldVerification.MISSING

    def test_numeric_field(self) -> None:
        status, score = verify_field(
            "fundingTotal", "$7.3B",
            "raised $7.3 billion", "They raised $7.3 billion in funding",
        )
        assert isinstance(status, FieldVerification)

    def test_date_field(self) -> None:
        status, score = verify_field(
            "foundedDate", "2021",
            "founded in 2021", "The company was founded in 2021",
        )
        assert isinstance(status, FieldVerification)

    def test_url_field_without_protocol_match(self) -> None:
        """URL without protocol should still match (lines 86-88)."""
        status, score = verify_field(
            "website", "https://example.com/page",
            "example.com/page is their site",
            "Check out example.com/page for details",
        )
        assert status == FieldVerification.GROUNDED

    def test_url_field_not_in_source(self) -> None:
        """URL not found in source at all (line 90)."""
        status, score = verify_field(
            "website", "https://completely-different.com",
            "some evidence text",
            "Source text that does not contain the URL anywhere",
        )
        assert status == FieldVerification.UNVERIFIED
        assert score == 0.0


class TestAggregateVerification:
    def test_all_grounded(self) -> None:
        results = [
            ("f1", FieldVerification.GROUNDED, 0.99),
            ("f2", FieldVerification.GROUNDED, 0.95),
        ]
        status, ratio = aggregate_verification(results)
        assert status == VerificationStatus.GROUNDED
        assert ratio == 1.0

    def test_partial(self) -> None:
        results = [
            ("f1", FieldVerification.GROUNDED, 0.99),
            ("f2", FieldVerification.UNVERIFIED, 0.0),
        ]
        status, ratio = aggregate_verification(results)
        assert status == VerificationStatus.PARTIAL
        assert ratio == 0.5

    def test_unverified(self) -> None:
        results = [
            ("f1", FieldVerification.UNVERIFIED, 0.0),
            ("f2", FieldVerification.UNVERIFIED, 0.0),
            ("f3", FieldVerification.GROUNDED, 0.9),
        ]
        status, ratio = aggregate_verification(results)
        assert status == VerificationStatus.UNVERIFIED

    def test_rejected(self) -> None:
        results = [
            ("f1", FieldVerification.CONFLICTING, 0.5),
            ("f2", FieldVerification.GROUNDED, 0.9),
        ]
        status, ratio = aggregate_verification(results)
        assert status == VerificationStatus.REJECTED

    def test_empty(self) -> None:
        status, ratio = aggregate_verification([])
        assert status == VerificationStatus.UNVERIFIED
        assert ratio == 0.0
