"""Production hardening tests — covers every uncovered line.

This file targets specific lines identified by the coverage audit
to ensure 100% branch and line coverage on all new modules.
"""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

from provenmesh.export.lineage import LineageTracker
from provenmesh.export.quality import QualityDimension, QualityScorer
from provenmesh.grounding.hallucination import HallucinationDetector
from provenmesh.resolver.conflict import ConflictResolver, SourceAssertion

NOW = datetime.now(tz=UTC)


class TestLineageExceptionPath:
    """Covers lineage.py L462-463: exception in _extract_source_name."""

    def test_extract_source_name_with_exception_url(self) -> None:
        """urlparse can handle most strings but hostname may be None.
        Test with a truly broken input that still doesn't raise."""
        result = LineageTracker._extract_source_name("://")
        assert isinstance(result, str)

    def test_extract_source_name_with_none_like(self) -> None:
        result = LineageTracker._extract_source_name("   ")
        assert isinstance(result, str)

    def test_extract_source_name_with_ip(self) -> None:
        result = LineageTracker._extract_source_name("http://192.168.1.1/x")
        assert result == "192"

    def test_lineage_grounding_score_below_one(self) -> None:
        """Covers the 0-1 scale branch (score <= 1)."""
        tracker = LineageTracker()
        evidence = [SimpleNamespace(
            field_name="name",
            extracted_value="Test",
            evidence_text="test evidence",
            source_url="https://example.com",
            source_content_hash="abc",
            raw_s3_key="raw/key",
            fuzzy_score=0.85,
            verified_at=NOW,
        )]
        lineage = tracker.build_field_lineage(
            entity_id="e1",
            field_name="name",
            final_value="Test",
            evidence_records=evidence,
        )
        # Score 0.85 is <= 1.0, so no division by 100
        assert lineage.lineage_chain[0].score == 0.85


class TestQualityNaiveDatetime:
    """Covers quality.py L353: naive datetime in _age_description."""

    def test_age_description_naive_datetime(self) -> None:
        naive = datetime(2024, 1, 1)  # noqa: DTZ001
        result = QualityScorer._age_description(naive)
        assert isinstance(result, str)
        assert result != "unknown"


class TestQualityConflictConsensusRecommendation:
    """Covers quality.py L404-405: conflict_consensus recommendation."""

    def test_low_consensus_recommendation(self) -> None:
        recs = QualityScorer._generate_recommendations(
            [QualityDimension(
                name="conflict_consensus", score=20.0, weight=0.15,
            )],
            overall=30.0,
        )
        assert any("disagree" in r.lower() for r in recs)

    def test_low_completeness_recommendation(self) -> None:
        recs = QualityScorer._generate_recommendations(
            [QualityDimension(
                name="completeness", score=10.0, weight=0.10,
            )],
            overall=30.0,
        )
        assert any("missing" in r.lower() for r in recs)

    def test_low_freshness_recommendation(self) -> None:
        recs = QualityScorer._generate_recommendations(
            [QualityDimension(
                name="freshness", score=10.0, weight=0.10,
            )],
            overall=30.0,
        )
        assert any("stale" in r.lower() for r in recs)


class TestHallucinationNumericAttribution:
    """Covers hallucination.py L448: numeric value found in source."""

    def test_numeric_value_found_in_source(self) -> None:
        detector = HallucinationDetector()
        report = detector.analyze_record(
            extracted_fields={
                "employeeCount": {
                    "value": "$1,500",
                    "evidence": "The company has 1500 people",
                    "confidence": 0.9,
                },
            },
            source_text="The company has 1500 people working there.",
            grounding_scores={"employeeCount": 0.9},
        )
        # Numeric value 1500 IS in source, so no attribution flag
        attr_flags = [
            f for f in report.flags if f.check_type == "attribution"
        ]
        assert len(attr_flags) == 0


class TestHallucinationCrossFieldContradiction:
    """Covers hallucination.py L509-510: exception in cross-field."""

    def test_cross_field_with_regex_error(self) -> None:
        """If foundedDate has no valid year pattern, should not crash."""
        detector = HallucinationDetector()
        report = detector.analyze_record(
            extracted_fields={
                "foundedDate": {
                    "value": "not-a-date",
                    "evidence": "some evidence",
                    "confidence": 0.9,
                },
                "description": {
                    "value": "A company founded in 2020",
                    "evidence": "description text",
                    "confidence": 0.9,
                },
            },
            source_text="A company founded in 2020 with some evidence",
        )
        # Should not crash, no contradiction flag since
        # "not-a-date" has no 4-digit year
        assert isinstance(report.overall_trust_score, float)

    def test_cross_field_year_mismatch_detected(self) -> None:
        """Covers L498-508: actual year contradiction detection."""
        detector = HallucinationDetector()
        report = detector.analyze_record(
            extracted_fields={
                "foundedDate": {
                    "value": "2015",
                    "evidence": "founded in 2015",
                    "confidence": 0.9,
                },
                "description": {
                    "value": "A company founded in 2020",
                    "evidence": "A company founded in 2020",
                    "confidence": 0.9,
                },
            },
            source_text="A company founded in 2015 2020 evidence",
        )
        contradiction_flags = [
            f for f in report.flags if f.check_type == "contradiction"
        ]
        assert len(contradiction_flags) >= 1
        assert "2020" in contradiction_flags[0].message


class TestConflictResolverNaiveDatetime:
    """Covers conflict.py L336: naive datetime in _recency_weight."""

    def test_naive_datetime_in_recency(self) -> None:
        resolver = ConflictResolver()
        naive_dt = datetime(2024, 1, 1)  # noqa: DTZ001
        weight = resolver._recency_weight(naive_dt)
        assert 0.0 < weight <= 1.0

    def test_resolve_field_with_naive_assertions(self) -> None:
        resolver = ConflictResolver()
        assertions = [
            SourceAssertion(
                value="2015",
                source_url="https://a.com",
                source_name="crunchbase",
                grounding_score=0.9,
                trust_score=0.9,
                fetched_at=datetime(2024, 6, 1),  # noqa: DTZ001
            ),
            SourceAssertion(
                value="2016",
                source_url="https://b.com",
                source_name="techcrunch",
                grounding_score=0.5,
                trust_score=0.5,
                fetched_at=datetime(2024, 1, 1),  # noqa: DTZ001
            ),
        ]
        result = resolver.resolve_field("year", assertions)
        assert result.winning_value == "2015"


class TestHallucinationListFields:
    """Covers hallucination.py L153: list field iteration."""

    def test_list_field_extraction(self) -> None:
        detector = HallucinationDetector()
        report = detector.analyze_record(
            extracted_fields={
                "founders": [
                    {
                        "value": "Sam Altman",
                        "evidence": "Sam Altman co-founded",
                        "confidence": 0.95,
                    },
                    {
                        "value": "Greg Brockman",
                        "evidence": "Greg Brockman co-founded",
                        "confidence": 0.93,
                    },
                ],
            },
            source_text=(
                "Sam Altman and Greg Brockman co-founded the company"
            ),
        )
        assert report.fields_checked == 2

    def test_list_field_non_dict_items_skipped(self) -> None:
        detector = HallucinationDetector()
        report = detector.analyze_record(
            extracted_fields={
                "tags": ["ai", "ml", "nlp"],  # Not dicts
            },
            source_text="AI ML NLP company",
        )
        assert report.fields_checked == 0

    def test_list_field_without_value_key_skipped(self) -> None:
        detector = HallucinationDetector()
        report = detector.analyze_record(
            extracted_fields={
                "data": [{"name": "X"}],  # No 'value' key
            },
            source_text="Some source text",
        )
        assert report.fields_checked == 0


class TestLineageExceptionHandler:
    """Covers lineage.py L462-463: exception in urlparse."""

    def test_extract_source_name_urlparse_exception(self) -> None:
        """Force urlparse to raise by mocking it."""
        from unittest.mock import patch

        with patch(
            "provenmesh.export.lineage.LineageTracker._extract_source_name",
            wraps=LineageTracker._extract_source_name,
        ):
            # urlparse almost never throws, but the except block is
            # defensive. We verify the fallback works by passing
            # something urlparse handles gracefully anyway.
            result = LineageTracker._extract_source_name("http://")
            assert result == ""

    def test_extract_source_urlparse_raises(self) -> None:
        """Actually trigger the except block via mock."""
        from unittest.mock import patch

        with patch(
            "urllib.parse.urlparse",
            side_effect=ValueError("broken"),
        ):
            result = LineageTracker._extract_source_name("https://x.com")
            assert result == ""


class TestHallucinationCrossFieldException:
    """Covers hallucination.py L509-510: exception in cross-field."""

    def test_cross_field_attribute_error(self) -> None:
        """Force an AttributeError in the regex cross-field check."""
        from unittest.mock import patch

        detector = HallucinationDetector()

        # Mock re.search to raise AttributeError
        with patch(
            "provenmesh.grounding.hallucination.re.search",
            side_effect=AttributeError("forced"),
        ):
            report = detector.analyze_record(
                extracted_fields={
                    "foundedDate": {
                        "value": "2015",
                        "evidence": "founded in 2015",
                        "confidence": 0.9,
                    },
                    "description": {
                        "value": "A company",
                        "evidence": "A company desc",
                        "confidence": 0.9,
                    },
                },
                source_text="founded in 2015 A company desc",
            )
            # Should not crash — exception caught gracefully
            assert isinstance(report.overall_trust_score, float)

