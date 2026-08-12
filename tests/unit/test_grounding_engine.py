"""Tests for grounding/engine.py — GroundingEngine evidence verification."""
from __future__ import annotations

from provenmesh.domain.enums import FieldVerification, VerificationStatus
from provenmesh.grounding.engine import GroundingEngine, GroundingResult


class TestGroundingEngine:
    def test_verify_record_empty(self) -> None:
        engine = GroundingEngine()
        result = engine.verify_record({}, "some source text")
        assert result.verification_status == VerificationStatus.UNVERIFIED
        assert result.total_count == 0

    def test_verify_text_field_grounded(self) -> None:
        engine = GroundingEngine()
        fields = {
            "entityName": {
                "value": "OpenAI",
                "evidence": "OpenAI is an AI research company",
                "confidence": 0.95,
            },
        }
        source = "OpenAI is an AI research company founded in 2015."
        result = engine.verify_record(fields, source)
        assert result.total_count == 1
        assert result.grounded_count == 1
        assert result.verification_status == VerificationStatus.GROUNDED

    def test_verify_text_field_unverified(self) -> None:
        engine = GroundingEngine()
        fields = {
            "entityName": {
                "value": "OpenAI",
                "evidence": "Completely fabricated evidence text xyz abc",
                "confidence": 0.95,
            },
        }
        source = "This source is about cooking recipes and has nothing about AI."
        result = engine.verify_record(fields, source)
        assert result.verification_status == VerificationStatus.UNVERIFIED

    def test_verify_missing_value(self) -> None:
        engine = GroundingEngine()
        fields = {
            "entityName": {"value": None, "evidence": "text", "confidence": 0.5},
        }
        result = engine.verify_record(fields, "source")
        assert result.total_count == 1
        assert result.evidence_records[0].verification_status == FieldVerification.MISSING

    def test_verify_empty_value(self) -> None:
        engine = GroundingEngine()
        fields = {
            "entityName": {"value": "", "evidence": "text", "confidence": 0.5},
        }
        result = engine.verify_record(fields, "source")
        assert result.evidence_records[0].verification_status == FieldVerification.MISSING

    def test_verify_no_evidence(self) -> None:
        engine = GroundingEngine()
        fields = {
            "entityName": {"value": "OpenAI", "confidence": 0.9},
        }
        result = engine.verify_record(fields, "source text with OpenAI")
        assert result.evidence_records[0].verification_status == FieldVerification.UNVERIFIED

    def test_verify_list_fields(self) -> None:
        engine = GroundingEngine()
        fields = {
            "founders": [
                {"value": "Sam Altman", "evidence": "Sam Altman co-founded", "confidence": 0.9},
                {
                    "value": "Greg Brockman",
                    "evidence": "Greg Brockman was involved",
                    "confidence": 0.8,
                },
            ],
        }
        source = "Sam Altman co-founded OpenAI. Greg Brockman was involved as CTO."
        result = engine.verify_record(fields, source)
        assert result.total_count == 2

    def test_verify_url_field(self) -> None:
        engine = GroundingEngine()
        fields = {
            "website": {
                "value": "https://openai.com",
                "evidence": "Visit https://openai.com for more",
                "confidence": 0.99,
            },
        }
        source = "Visit https://openai.com for more information about the company."
        result = engine.verify_record(fields, source)
        assert result.grounded_count >= 1

    def test_verify_number_field(self) -> None:
        engine = GroundingEngine()
        fields = {
            "funding": {
                "value": "$6,600,000,000",
                "evidence": "OpenAI raised $6.6B in funding",
                "confidence": 0.9,
            },
        }
        source = "OpenAI raised $6.6B in funding during their latest round."
        result = engine.verify_record(fields, source)
        assert result.total_count == 1

    def test_overall_partial(self) -> None:
        engine = GroundingEngine()
        fields = {
            "name": {"value": "OpenAI", "evidence": "OpenAI is here", "confidence": 0.9},
            "fake": {"value": "Fake Data", "evidence": "Fabricated xyz abc", "confidence": 0.9},
        }
        source = "OpenAI is here but nothing about fake data or fabricated content."
        result = engine.verify_record(fields, source, entity_id="test")
        assert result.total_count == 2

    def test_source_url_and_hash_propagated(self) -> None:
        engine = GroundingEngine()
        fields = {"name": {"value": "Test", "evidence": "Test evidence", "confidence": 0.5}}
        result = engine.verify_record(
            fields, "Test evidence here",
            source_url="https://example.com",
            content_hash="abc123",
        )
        rec = result.evidence_records[0]
        assert rec.source_url == "https://example.com"
        assert rec.source_content_hash == "abc123"


class TestGroundingHelpers:
    def test_looks_like_number(self) -> None:
        engine = GroundingEngine()
        assert engine._looks_like_number("42") is True
        assert engine._looks_like_number("$6.6B") is True
        assert engine._looks_like_number("1,500") is True
        assert engine._looks_like_number("OpenAI") is False

    def test_looks_like_url(self) -> None:
        engine = GroundingEngine()
        assert engine._looks_like_url("https://example.com") is True
        assert engine._looks_like_url("http://test.com") is True
        assert engine._looks_like_url("www.example.com") is True
        assert engine._looks_like_url("example.com") is False

    def test_extract_number(self) -> None:
        assert GroundingEngine._extract_number("42") == 42.0
        assert GroundingEngine._extract_number("$6.6B") == 6_600_000_000.0
        assert GroundingEngine._extract_number("$50M") == 50_000_000.0
        assert GroundingEngine._extract_number("5K") == 5_000.0
        assert GroundingEngine._extract_number("not a number") is None

    def test_verify_url(self) -> None:
        engine = GroundingEngine()
        ok, score = engine._verify_url("https://openai.com", "Visit https://openai.com here")
        assert ok is True
        assert score == 100.0

        ok, score = engine._verify_url("https://missing.com", "No such URL here")
        assert ok is False

    def test_verify_text(self) -> None:
        engine = GroundingEngine()
        ok, score = engine._verify_text(
            "OpenAI is an AI company",
            "OpenAI is an AI company founded in 2015",
        )
        assert ok is True
        assert score >= 90


class TestGroundingResult:
    def test_creation(self) -> None:
        r = GroundingResult(
            verification_status=VerificationStatus.GROUNDED,
            evidence_records=[],
            grounded_count=5,
            total_count=5,
        )
        assert r.verification_status == VerificationStatus.GROUNDED
        assert r.grounded_count == 5


class TestExtractNumberEdgeCases:
    def test_suffix_with_invalid_number(self) -> None:
        """Invalid number before suffix (lines 250-251)."""
        assert GroundingEngine._extract_number("$B") is None
        assert GroundingEngine._extract_number("abcM") is None

    def test_empty_string(self) -> None:
        assert GroundingEngine._extract_number("") is None
        assert GroundingEngine._extract_number("  ") is None

    def test_currency_only(self) -> None:
        assert GroundingEngine._extract_number("$") is None
        assert GroundingEngine._extract_number("€") is None


class TestVerifyNumberEdgeCases:
    def test_unparseable_number_falls_to_text(self) -> None:
        """When _extract_number returns None, falls back to text (line 199)."""
        engine = GroundingEngine()
        fields = {
            "fundingTotal": {
                "value": "about six billion",
                "evidence": "They raised about six billion",
                "confidence": 0.9,
            },
        }
        source = "They raised about six billion in capital."
        result = engine.verify_record(fields, source)
        assert result.total_count == 1

    def test_number_with_low_evidence_score(self) -> None:
        """Evidence doesn't match source text at all (line 204)."""
        engine = GroundingEngine()
        fields = {
            "revenue": {
                "value": "$500M",
                "evidence": "completely unrelated xyz text",
                "confidence": 0.9,
            },
        }
        source = "The company made $500M last year."
        result = engine.verify_record(fields, source)
        assert result.total_count == 1


class TestVerifyNumberException:
    def test_verify_number_valueerror_fallback(self) -> None:
        """When _verify_number hits ValueError/TypeError (lines 217-218)."""
        from unittest.mock import patch
        engine = GroundingEngine()
        # Patch _extract_number to raise ValueError
        with patch.object(
            GroundingEngine, "_extract_number",
            side_effect=ValueError("bad value"),
        ):
            ok, score = engine._verify_number(
                "$5B", "they raised $5 billion", "They raised $5 billion.",
            )
            # Should fall back to _verify_text
            assert isinstance(ok, bool)

    def test_verify_number_typeerror_fallback(self) -> None:
        """When _verify_number hits TypeError (lines 217-218)."""
        from unittest.mock import patch
        engine = GroundingEngine()
        with patch.object(
            GroundingEngine, "_extract_number",
            side_effect=TypeError("type error"),
        ):
            ok, score = engine._verify_number(
                "100", "evidence about 100", "Source text about 100.",
            )
            assert isinstance(ok, bool)

    def test_verify_number_none_fallback_to_text(self) -> None:
        """When _extract_number returns None → fallback to text (line 199)."""
        engine = GroundingEngine()
        ok, score = engine._verify_number(
            "approximately five billion",
            "approximately five billion in revenue",
            "approximately five billion in revenue was reported.",
        )
        assert isinstance(ok, bool)


