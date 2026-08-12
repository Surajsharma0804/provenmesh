"""Unit tests for the grounding engine — evidence verification."""

from __future__ import annotations

import pytest

from provenmesh.domain.enums import FieldVerification, VerificationStatus
from provenmesh.grounding.engine import GroundingEngine


@pytest.fixture
def engine() -> GroundingEngine:
    return GroundingEngine()


SOURCE_TEXT = """
OpenAI is an artificial intelligence research company headquartered in
San Francisco, California. Founded in December 2015 by Sam Altman,
Greg Brockman, Elon Musk, and others, the company has raised over
$11.3 billion in funding. OpenAI employs approximately 1,700 people
and is valued at $80 billion as of 2024.
"""


class TestTextGrounding:
    """Tests for text field grounding."""

    def test_exact_evidence_match(self, engine: GroundingEngine) -> None:
        fields = {
            "entityName": {
                "value": "OpenAI",
                "evidence": "OpenAI is an artificial intelligence research company",
                "confidence": 0.95,
            }
        }
        result = engine.verify_record(fields, SOURCE_TEXT)
        assert result.verification_status in (VerificationStatus.GROUNDED, VerificationStatus.PARTIAL)  # noqa: E501
        assert result.grounded_count >= 1

    def test_hallucinated_evidence_fails(self, engine: GroundingEngine) -> None:
        fields = {
            "entityName": {
                "value": "OpenAI",
                "evidence": "OpenAI was founded in Tokyo by Japanese investors",
                "confidence": 0.95,
            }
        }
        result = engine.verify_record(fields, SOURCE_TEXT)
        assert result.evidence_records[0].verification_status == FieldVerification.UNVERIFIED

    def test_missing_evidence(self, engine: GroundingEngine) -> None:
        fields = {
            "entityName": {
                "value": "OpenAI",
                "evidence": "",
                "confidence": 0.95,
            }
        }
        result = engine.verify_record(fields, SOURCE_TEXT)
        assert result.evidence_records[0].verification_status == FieldVerification.UNVERIFIED

    def test_null_value(self, engine: GroundingEngine) -> None:
        fields = {
            "entityName": {
                "value": None,
                "evidence": "",
                "confidence": 0.0,
            }
        }
        result = engine.verify_record(fields, SOURCE_TEXT)
        assert result.evidence_records[0].verification_status == FieldVerification.MISSING


class TestNumericGrounding:
    """Tests for numeric field grounding."""

    def test_exact_number(self, engine: GroundingEngine) -> None:
        fields = {
            "employeeCount": {
                "value": "1700",
                "evidence": "OpenAI employs approximately 1,700 people",
                "confidence": 0.90,
            }
        }
        result = engine.verify_record(fields, SOURCE_TEXT)
        grounded = any(
            r.verification_status == FieldVerification.GROUNDED
            for r in result.evidence_records
        )
        assert grounded

    def test_funding_with_suffix(self, engine: GroundingEngine) -> None:
        fields = {
            "fundingTotal": {
                "value": "$11.3B",
                "evidence": "the company has raised over $11.3 billion in funding",
                "confidence": 0.92,
            }
        }
        result = engine.verify_record(fields, SOURCE_TEXT)
        assert result.grounded_count >= 1


class TestUrlGrounding:
    """Tests for URL field grounding."""

    def test_url_in_source(self, engine: GroundingEngine) -> None:
        source = "Visit us at https://openai.com for more information."
        fields = {
            "website": {
                "value": "https://openai.com",
                "evidence": "Visit us at https://openai.com",
                "confidence": 0.99,
            }
        }
        result = engine.verify_record(fields, source)
        assert result.grounded_count == 1

    def test_url_not_in_source(self, engine: GroundingEngine) -> None:
        source = "The company operates from San Francisco."
        fields = {
            "website": {
                "value": "https://openai.com",
                "evidence": "",
                "confidence": 0.5,
            }
        }
        result = engine.verify_record(fields, source)
        assert result.grounded_count == 0


class TestRecordVerification:
    """Tests for overall record verification status."""

    def test_fully_grounded(self, engine: GroundingEngine) -> None:
        fields = {
            "entityName": {
                "value": "OpenAI",
                "evidence": "OpenAI is an artificial intelligence research company",
                "confidence": 0.95,
            },
            "headquarters": {
                "value": "San Francisco",
                "evidence": "headquartered in San Francisco, California",
                "confidence": 0.92,
            },
        }
        result = engine.verify_record(fields, SOURCE_TEXT)
        assert result.verification_status == VerificationStatus.GROUNDED
        assert result.grounding_ratio == 1.0

    def test_empty_fields(self, engine: GroundingEngine) -> None:
        result = engine.verify_record({}, SOURCE_TEXT)
        assert result.verification_status == VerificationStatus.UNVERIFIED
        assert result.grounding_ratio == 0.0

    def test_grounding_result_exportable(self, engine: GroundingEngine) -> None:
        fields = {
            "entityName": {
                "value": "OpenAI",
                "evidence": "OpenAI is an artificial intelligence research company",
                "confidence": 0.95,
            },
        }
        result = engine.verify_record(fields, SOURCE_TEXT)
        assert result.is_exportable
