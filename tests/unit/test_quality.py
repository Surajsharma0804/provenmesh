"""Tests for data quality scoring engine.

Covers:
    - QualityGrade enum and from_score boundaries
    - QualityDimension weighted scoring
    - QualityReport serialization
    - QualityScorer: all 6 dimensions, grading, export gating,
      recommendations, edge cases
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from provenmesh.export.quality import (
    QualityDimension,
    QualityGrade,
    QualityReport,
    QualityScorer,
)

NOW = datetime.now(tz=UTC)


class TestQualityGrade:
    def test_grade_a(self) -> None:
        assert QualityGrade.from_score(95) == QualityGrade.A
        assert QualityGrade.from_score(90) == QualityGrade.A

    def test_grade_b(self) -> None:
        assert QualityGrade.from_score(89) == QualityGrade.B
        assert QualityGrade.from_score(75) == QualityGrade.B

    def test_grade_c(self) -> None:
        assert QualityGrade.from_score(74) == QualityGrade.C
        assert QualityGrade.from_score(60) == QualityGrade.C

    def test_grade_d(self) -> None:
        assert QualityGrade.from_score(59) == QualityGrade.D
        assert QualityGrade.from_score(40) == QualityGrade.D

    def test_grade_f(self) -> None:
        assert QualityGrade.from_score(39) == QualityGrade.F
        assert QualityGrade.from_score(0) == QualityGrade.F

    def test_grade_100(self) -> None:
        assert QualityGrade.from_score(100) == QualityGrade.A


class TestQualityDimension:
    def test_weighted_score(self) -> None:
        d = QualityDimension(name="test", score=80.0, weight=0.25)
        assert d.weighted_score == pytest.approx(20.0)

    def test_zero_weight(self) -> None:
        d = QualityDimension(name="test", score=100.0, weight=0.0)
        assert d.weighted_score == 0.0


class TestQualityReport:
    def test_to_dict(self) -> None:
        report = QualityReport(
            entity_id="e1",
            entity_name="OpenAI",
            record_type="STARTUP",
            overall_score=87.5,
            grade=QualityGrade.B,
            export_allowed=True,
            dimensions=[
                QualityDimension(
                    name="grounding", score=90.0,
                    weight=0.25, details="avg=0.90",
                ),
            ],
            recommendations=["Looks good."],
        )
        d = report.to_dict()
        assert d["overall_score"] == 87.5
        assert d["grade"] == "B"
        assert d["export_allowed"] is True
        assert len(d["dimensions"]) == 1
        assert d["dimensions"][0]["name"] == "grounding"


class TestSourceDiversity:
    def test_zero_sources(self) -> None:
        assert QualityScorer._score_source_diversity(0) == 0.0

    def test_one_source(self) -> None:
        assert QualityScorer._score_source_diversity(1) == 40.0

    def test_two_sources(self) -> None:
        assert QualityScorer._score_source_diversity(2) == 70.0

    def test_three_sources(self) -> None:
        assert QualityScorer._score_source_diversity(3) == 85.0

    def test_many_sources_capped(self) -> None:
        score = QualityScorer._score_source_diversity(10)
        assert score <= 100.0
        assert score > 85.0


class TestGroundingScore:
    def test_empty_scores(self) -> None:
        assert QualityScorer._score_grounding([]) == 0.0

    def test_normalized_scores(self) -> None:
        assert QualityScorer._score_grounding([0.9, 0.8]) == pytest.approx(85.0)

    def test_raw_fuzzy_scores(self) -> None:
        """Scores > 1 are treated as 0-100 scale."""
        assert QualityScorer._score_grounding([90.0, 80.0]) == pytest.approx(85.0)

    def test_mixed_scores(self) -> None:
        score = QualityScorer._score_grounding([0.95])
        assert score == pytest.approx(95.0)


class TestCompleteness:
    def test_all_fields_present(self) -> None:
        assert QualityScorer._score_completeness(5, 5) == 100.0

    def test_half_fields(self) -> None:
        assert QualityScorer._score_completeness(3, 6) == 50.0

    def test_no_requirements(self) -> None:
        assert QualityScorer._score_completeness(0, 0) == 100.0

    def test_zero_present(self) -> None:
        assert QualityScorer._score_completeness(0, 5) == 0.0


class TestFreshness:
    def test_no_fetch_date(self) -> None:
        scorer = QualityScorer()
        assert scorer._score_freshness(None) == 0.0

    def test_today(self) -> None:
        scorer = QualityScorer()
        score = scorer._score_freshness(NOW)
        assert score >= 95.0

    def test_30_days_old(self) -> None:
        scorer = QualityScorer()
        old = NOW - timedelta(days=30)
        score = scorer._score_freshness(old)
        assert 45.0 <= score <= 55.0  # ~50 (half-life)

    def test_very_old(self) -> None:
        scorer = QualityScorer()
        old = NOW - timedelta(days=365)
        score = scorer._score_freshness(old)
        assert score >= 10.0  # Minimum floor
        assert score < 20.0

    def test_naive_datetime(self) -> None:
        scorer = QualityScorer()
        naive = datetime(2024, 1, 1)  # noqa: DTZ001
        score = scorer._score_freshness(naive)
        assert score >= 10.0

    def test_future_date(self) -> None:
        scorer = QualityScorer()
        future = NOW + timedelta(hours=1)
        score = scorer._score_freshness(future)
        assert score == 100.0


class TestAgeDescription:
    def test_today(self) -> None:
        assert QualityScorer._age_description(NOW) == "today"

    def test_yesterday(self) -> None:
        result = QualityScorer._age_description(NOW - timedelta(days=1))
        assert result == "1 day ago"

    def test_days(self) -> None:
        result = QualityScorer._age_description(NOW - timedelta(days=15))
        assert result == "15 days ago"

    def test_months(self) -> None:
        result = QualityScorer._age_description(NOW - timedelta(days=60))
        assert "month" in result

    def test_years(self) -> None:
        result = QualityScorer._age_description(NOW - timedelta(days=400))
        assert "year" in result

    def test_none(self) -> None:
        assert QualityScorer._age_description(None) == "unknown"


class TestFullEntityScoring:
    def test_excellent_entity(self) -> None:
        scorer = QualityScorer()
        report = scorer.score_entity(
            entity_id="e1",
            entity_name="OpenAI",
            record_type="STARTUP",
            source_count=4,
            grounding_scores=[0.95, 0.92, 0.88, 0.90],
            trust_score=0.97,
            consensus_ratio=1.0,
            fields_present=5,
            fields_required=5,
            latest_fetch=NOW,
        )
        assert report.overall_score >= 85.0
        assert report.grade in (QualityGrade.A, QualityGrade.B)
        assert report.export_allowed
        assert not report.needs_recrawl

    def test_poor_entity(self) -> None:
        scorer = QualityScorer()
        report = scorer.score_entity(
            entity_id="e2",
            entity_name="Unknown Corp",
            source_count=1,
            grounding_scores=[0.30],
            trust_score=0.40,
            consensus_ratio=0.50,
            fields_present=1,
            fields_required=5,
            latest_fetch=NOW - timedelta(days=90),
        )
        assert report.overall_score < 60.0
        assert report.grade in (QualityGrade.D, QualityGrade.F)
        assert not report.export_allowed
        assert report.needs_recrawl
        assert len(report.recommendations) > 0

    def test_missing_data_degrades_gracefully(self) -> None:
        scorer = QualityScorer()
        report = scorer.score_entity(
            entity_id="e3",
            entity_name="Mystery Corp",
        )
        assert report.overall_score >= 0.0
        assert report.grade in (QualityGrade.D, QualityGrade.F)
        assert not report.export_allowed

    def test_review_band(self) -> None:
        """Entities between 60-75 should need review."""
        scorer = QualityScorer()
        report = scorer.score_entity(
            entity_id="e4",
            source_count=2,
            grounding_scores=[0.65],
            trust_score=0.70,
            consensus_ratio=0.80,
            fields_present=3,
            fields_required=5,
            latest_fetch=NOW - timedelta(days=15),
        )
        if 60 <= report.overall_score < 75:
            assert report.needs_review

    def test_custom_weights(self) -> None:
        scorer = QualityScorer(weights={
            "source_diversity": 0.0,
            "grounding_strength": 1.0,
            "hallucination_risk": 0.0,
            "conflict_consensus": 0.0,
            "completeness": 0.0,
            "freshness": 0.0,
        })
        report = scorer.score_entity(
            entity_id="e5",
            grounding_scores=[0.95],
        )
        assert report.overall_score == pytest.approx(95.0)

    def test_custom_thresholds(self) -> None:
        scorer = QualityScorer(export_threshold=80.0)
        report = scorer.score_entity(
            entity_id="e6",
            source_count=2,
            grounding_scores=[0.70],
            trust_score=0.75,
        )
        if report.overall_score < 80.0:
            assert not report.export_allowed

    def test_recommendations_for_weak_dims(self) -> None:
        scorer = QualityScorer()
        report = scorer.score_entity(
            entity_id="e7",
            source_count=0,
            grounding_scores=[],
            trust_score=0.20,
            fields_present=0,
            fields_required=10,
        )
        assert len(report.recommendations) >= 2

    def test_excellent_gets_positive_recommendation(self) -> None:
        scorer = QualityScorer()
        report = scorer.score_entity(
            entity_id="e8",
            source_count=5,
            grounding_scores=[0.98, 0.95, 0.97],
            trust_score=0.99,
            consensus_ratio=1.0,
            fields_present=5,
            fields_required=5,
            latest_fetch=NOW,
        )
        if report.overall_score >= 90:
            assert any("Excellent" in r for r in report.recommendations)

    def test_report_to_dict_has_all_dimensions(self) -> None:
        scorer = QualityScorer()
        report = scorer.score_entity(
            entity_id="e9",
            source_count=3,
            grounding_scores=[0.90],
            trust_score=0.95,
        )
        d = report.to_dict()
        assert len(d["dimensions"]) == 6
        dim_names = {dim["name"] for dim in d["dimensions"]}
        assert "source_diversity" in dim_names
        assert "grounding_strength" in dim_names
        assert "hallucination_risk" in dim_names
        assert "conflict_consensus" in dim_names
        assert "completeness" in dim_names
        assert "freshness" in dim_names
