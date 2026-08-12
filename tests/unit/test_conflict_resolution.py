"""Tests for multi-source conflict resolution.

Covers:
    - Single source resolution (capped confidence)
    - Unanimous agreement (all sources agree)
    - Majority voting (2 vs 1 sources)
    - Quality-based winner (tie broken by evidence quality)
    - Recency weighting (fresher data wins ties)
    - Source credibility (known vs unknown sources)
    - Dissent audit trail
    - Full record resolution
    - Edge cases (empty, whitespace normalization, etc.)
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from provenmesh.resolver.conflict import (
    ConflictReport,
    ConflictResolver,
    FieldResolution,
    SourceAssertion,
)

# ─── Helpers ──────────────────────────────────────────────────────

def _make_assertion(
    value: str,
    source_name: str = "crunchbase",
    grounding: float = 0.95,
    trust: float = 0.97,
    confidence: float = 0.95,
    days_ago: int = 0,
    evidence: str = "",
) -> SourceAssertion:
    """Create a SourceAssertion with sensible defaults."""
    return SourceAssertion(
        value=value,
        source_url=f"https://{source_name}.com/openai",
        source_name=source_name,
        grounding_score=grounding,
        trust_score=trust,
        llm_confidence=confidence,
        fetched_at=datetime.now(tz=UTC) - timedelta(days=days_ago),
        evidence_text=evidence or f"Evidence for {value}",
    )


NOW = datetime.now(tz=UTC)


class TestSourceAssertion:
    def test_frozen_dataclass(self) -> None:
        a = _make_assertion("OpenAI")
        with pytest.raises(AttributeError):
            a.value = "changed"  # type: ignore[misc]

    def test_default_timestamp(self) -> None:
        a = SourceAssertion(value="test", source_url="https://x.com")
        assert a.fetched_at is not None
        assert (NOW - a.fetched_at).total_seconds() < 5


class TestFieldResolution:
    def test_dissent_summary_empty(self) -> None:
        r = FieldResolution(field_name="test", winning_value="x")
        assert r.dissent_summary == ""

    def test_dissent_summary_with_dissenters(self) -> None:
        r = FieldResolution(
            field_name="test",
            winning_value="2015",
            dissenting_assertions=[
                _make_assertion("2016", "venturebeat"),
                _make_assertion("2017", "techcrunch"),
            ],
        )
        assert "venturebeat" in r.dissent_summary
        assert "techcrunch" in r.dissent_summary
        assert "2016" in r.dissent_summary

    def test_dissent_summary_uses_source_url_fallback(self) -> None:
        r = FieldResolution(
            field_name="test",
            winning_value="2015",
            dissenting_assertions=[
                SourceAssertion(
                    value="2016",
                    source_url="https://example.com",
                    source_name="",
                ),
            ],
        )
        assert "https://example.com" in r.dissent_summary


class TestConflictReport:
    def test_empty_report(self) -> None:
        r = ConflictReport()
        assert not r.has_conflicts
        assert r.consensus_ratio == 0.0
        assert r.get_winning_values() == {}

    def test_has_conflicts(self) -> None:
        r = ConflictReport(contested_fields=["foundedDate"])
        assert r.has_conflicts

    def test_consensus_ratio(self) -> None:
        r = ConflictReport(total_fields=4, unanimous_fields=3)
        assert r.consensus_ratio == 0.75

    def test_get_winning_values(self) -> None:
        r = ConflictReport(
            field_resolutions={
                "name": FieldResolution(
                    field_name="name", winning_value="OpenAI",
                ),
                "year": FieldResolution(
                    field_name="year", winning_value="2015",
                ),
            },
        )
        vals = r.get_winning_values()
        assert vals == {"name": "OpenAI", "year": "2015"}


class TestSingleSourceResolution:
    def test_single_source_capped_at_07(self) -> None:
        resolver = ConflictResolver()
        result = resolver.resolve_field("name", [
            _make_assertion("OpenAI", grounding=0.99, trust=0.99),
        ])
        assert result.winning_value == "OpenAI"
        assert result.confidence <= 0.7
        assert result.resolution_method == "single_source"
        assert not result.is_contested

    def test_single_source_low_quality(self) -> None:
        resolver = ConflictResolver()
        result = resolver.resolve_field("name", [
            _make_assertion("OpenAI", grounding=0.3, trust=0.4),
        ])
        assert result.confidence == round(0.3 * 0.4, 4)

    def test_single_source_has_one_agreeing(self) -> None:
        resolver = ConflictResolver()
        result = resolver.resolve_field("name", [
            _make_assertion("OpenAI"),
        ])
        assert result.agreeing_sources == 1
        assert result.source_count == 1
        assert result.consensus_ratio == 1.0


class TestUnanimousAgreement:
    def test_all_sources_agree(self) -> None:
        resolver = ConflictResolver()
        assertions = [
            _make_assertion("2015", "crunchbase"),
            _make_assertion("2015", "techcrunch"),
            _make_assertion("2015", "linkedin"),
        ]
        result = resolver.resolve_field("foundedDate", assertions)
        assert result.winning_value == "2015"
        assert result.resolution_method == "unanimous"
        assert not result.is_contested
        assert result.agreeing_sources == 3
        assert result.consensus_ratio == 1.0
        assert len(result.dissenting_assertions) == 0

    def test_unanimous_case_insensitive(self) -> None:
        resolver = ConflictResolver()
        assertions = [
            _make_assertion("OpenAI", "crunchbase"),
            _make_assertion("openai", "techcrunch"),
            _make_assertion("OPENAI", "linkedin"),
        ]
        result = resolver.resolve_field("name", assertions)
        assert result.resolution_method == "unanimous"
        assert not result.is_contested

    def test_unanimous_whitespace_normalization(self) -> None:
        resolver = ConflictResolver()
        assertions = [
            _make_assertion("San Francisco", "crunchbase"),
            _make_assertion("  San   Francisco  ", "techcrunch"),
        ]
        result = resolver.resolve_field("hq", assertions)
        assert result.resolution_method == "unanimous"
        assert not result.is_contested


class TestMajorityVoting:
    def test_two_vs_one(self) -> None:
        resolver = ConflictResolver()
        assertions = [
            _make_assertion("2015", "crunchbase", grounding=0.95),
            _make_assertion("2015", "techcrunch", grounding=0.92),
            _make_assertion("2016", "venturebeat", grounding=0.88),
        ]
        result = resolver.resolve_field("foundedDate", assertions)
        assert result.winning_value == "2015"
        assert result.resolution_method == "majority_vote"
        assert result.is_contested
        assert result.agreeing_sources == 2
        assert len(result.dissenting_assertions) == 1
        assert result.dissenting_assertions[0].value == "2016"

    def test_three_vs_one(self) -> None:
        resolver = ConflictResolver()
        assertions = [
            _make_assertion("$11B", "crunchbase"),
            _make_assertion("$11B", "pitchbook"),
            _make_assertion("$11B", "techcrunch"),
            _make_assertion("$13B", "venturebeat", grounding=0.50),
        ]
        result = resolver.resolve_field("funding", assertions)
        assert result.winning_value == "$11B"
        assert result.agreeing_sources == 3
        assert result.consensus_ratio == 0.75


class TestQualityBasedWinner:
    def test_quality_breaks_tie(self) -> None:
        """When each value has 1 source, quality determines winner."""
        resolver = ConflictResolver()
        assertions = [
            _make_assertion(
                "2015", "crunchbase",
                grounding=0.98, trust=0.99,
            ),
            _make_assertion(
                "2016", "venturebeat",
                grounding=0.60, trust=0.50,
            ),
        ]
        result = resolver.resolve_field("foundedDate", assertions)
        assert result.winning_value == "2015"
        assert result.resolution_method == "quality_winner"
        assert result.is_contested

    def test_low_quality_source_loses(self) -> None:
        resolver = ConflictResolver()
        assertions = [
            _make_assertion(
                "San Francisco", "crunchbase",
                grounding=0.95, trust=0.97,
            ),
            _make_assertion(
                "Palo Alto", "unknown_blog",
                grounding=0.40, trust=0.30,
            ),
        ]
        result = resolver.resolve_field("hq", assertions)
        assert result.winning_value == "San Francisco"


class TestRecencyWeighting:
    def test_fresher_data_preferred(self) -> None:
        """When quality is equal, fresher data wins."""
        resolver = ConflictResolver()
        assertions = [
            _make_assertion(
                "$15B", "crunchbase",
                grounding=0.90, trust=0.90, days_ago=1,
            ),
            _make_assertion(
                "$11B", "techcrunch",
                grounding=0.90, trust=0.90, days_ago=90,
            ),
        ]
        result = resolver.resolve_field("funding", assertions)
        assert result.winning_value == "$15B"

    def test_very_old_data_still_counts(self) -> None:
        """Old data gets minimum weight, not zero."""
        resolver = ConflictResolver()
        assertions = [
            _make_assertion(
                "2015", "crunchbase",
                grounding=0.90, trust=0.90, days_ago=365,
            ),
        ]
        result = resolver.resolve_field("year", assertions)
        assert result.winning_value == "2015"
        assert result.confidence > 0.0

    def test_recency_half_life_custom(self) -> None:
        """Custom half-life changes decay rate."""
        fast_decay = ConflictResolver(recency_half_life_days=7.0)
        slow_decay = ConflictResolver(recency_half_life_days=365.0)

        # Use two sources so we avoid single-source 0.7 cap
        assertions = [
            _make_assertion(
                "2015", "crunchbase",
                grounding=0.90, trust=0.90, days_ago=30,
            ),
            _make_assertion(
                "2015", "techcrunch",
                grounding=0.90, trust=0.90, days_ago=30,
            ),
        ]

        fast_result = fast_decay.resolve_field("y", assertions)
        slow_result = slow_decay.resolve_field("y", assertions)

        # Faster decay = lower confidence for old data
        assert fast_result.confidence < slow_result.confidence


class TestSourceCredibility:
    def test_known_source_higher_weight(self) -> None:
        resolver = ConflictResolver()
        assertions = [
            _make_assertion(
                "2015", "crunchbase",
                grounding=0.90, trust=0.90,
            ),
            _make_assertion(
                "2016", "unknown_blog",
                grounding=0.90, trust=0.90,
            ),
        ]
        result = resolver.resolve_field("year", assertions)
        # Crunchbase (0.95 credibility) should beat unknown (0.75)
        assert result.winning_value == "2015"

    def test_custom_credibility_override(self) -> None:
        resolver = ConflictResolver(
            source_credibility={"my_source": 1.0},
        )
        assertions = [
            _make_assertion(
                "2015", "crunchbase",
                grounding=0.90, trust=0.90,
            ),
            _make_assertion(
                "2016", "my_source",
                grounding=0.90, trust=0.90,
            ),
        ]
        result = resolver.resolve_field("year", assertions)
        # Custom source has credibility 1.0 > crunchbase 0.95
        assert result.winning_value == "2016"

    def test_empty_source_name_uses_fallback(self) -> None:
        resolver = ConflictResolver()
        score = resolver._source_credibility("")
        assert score == 0.75  # _FALLBACK_CREDIBILITY


class TestFullRecordResolution:
    def test_resolve_record_all_unanimous(self) -> None:
        resolver = ConflictResolver()
        report = resolver.resolve_record(
            {
                "name": [
                    _make_assertion("OpenAI", "crunchbase"),
                    _make_assertion("OpenAI", "techcrunch"),
                ],
                "year": [
                    _make_assertion("2015", "crunchbase"),
                    _make_assertion("2015", "techcrunch"),
                ],
            },
            entity_id="openai-123",
        )
        assert report.total_fields == 2
        assert report.unanimous_fields == 2
        assert not report.has_conflicts
        assert report.overall_consensus > 0.0

    def test_resolve_record_with_conflicts(self) -> None:
        resolver = ConflictResolver()
        report = resolver.resolve_record(
            {
                "name": [
                    _make_assertion("OpenAI", "crunchbase"),
                    _make_assertion("OpenAI", "techcrunch"),
                ],
                "funding": [
                    _make_assertion("$11B", "crunchbase"),
                    _make_assertion("$13B", "techcrunch"),
                ],
            },
            entity_id="openai-123",
        )
        assert report.total_fields == 2
        assert report.has_conflicts
        assert "funding" in report.contested_fields
        assert "name" not in report.contested_fields

    def test_resolve_record_empty_assertions_skipped(self) -> None:
        resolver = ConflictResolver()
        report = resolver.resolve_record(
            {
                "name": [_make_assertion("OpenAI", "crunchbase")],
                "empty": [],
            },
        )
        assert report.total_fields == 1

    def test_winning_values_map(self) -> None:
        resolver = ConflictResolver()
        report = resolver.resolve_record(
            {
                "name": [_make_assertion("OpenAI", "crunchbase")],
                "year": [_make_assertion("2015", "techcrunch")],
            },
        )
        vals = report.get_winning_values()
        assert vals["name"] == "OpenAI"
        assert vals["year"] == "2015"


class TestEdgeCases:
    def test_identical_values_different_case(self) -> None:
        resolver = ConflictResolver()
        assertions = [
            _make_assertion("openai", "crunchbase"),
            _make_assertion("OpenAI", "techcrunch"),
        ]
        result = resolver.resolve_field("name", assertions)
        assert not result.is_contested  # Normalized match

    def test_value_with_extra_whitespace(self) -> None:
        resolver = ConflictResolver()
        assertions = [
            _make_assertion("  San  Francisco ", "crunchbase"),
            _make_assertion("San Francisco", "techcrunch"),
        ]
        result = resolver.resolve_field("hq", assertions)
        assert not result.is_contested

    def test_all_zero_scores(self) -> None:
        resolver = ConflictResolver()
        assertions = [
            _make_assertion(
                "X", "crunchbase",
                grounding=0.0, trust=0.0,
            ),
            _make_assertion(
                "Y", "techcrunch",
                grounding=0.0, trust=0.0,
            ),
        ]
        result = resolver.resolve_field("field", assertions)
        # Should not crash, picks one deterministically
        assert result.winning_value in ("X", "Y")

    def test_naive_datetime_handled(self) -> None:
        """Naive datetime should not crash recency calculation."""
        resolver = ConflictResolver()
        naive_assertion = SourceAssertion(
            value="2015",
            source_url="https://x.com",
            source_name="crunchbase",
            grounding_score=0.9,
            trust_score=0.9,
            fetched_at=datetime(2024, 1, 1),  # noqa: DTZ001
        )
        result = resolver.resolve_field("year", [naive_assertion])
        assert result.winning_value == "2015"

    def test_future_datetime_weight_is_one(self) -> None:
        """Future timestamps should get full recency weight."""
        resolver = ConflictResolver()
        future = datetime.now(tz=UTC) + timedelta(hours=1)
        a = SourceAssertion(
            value="2015",
            source_url="https://x.com",
            grounding_score=0.9,
            trust_score=0.9,
            fetched_at=future,
        )
        weight = resolver._recency_weight(a.fetched_at)
        assert weight == 1.0


class TestAuditTrail:
    def test_all_assertions_preserved(self) -> None:
        resolver = ConflictResolver()
        assertions = [
            _make_assertion("A", "crunchbase"),
            _make_assertion("B", "techcrunch"),
            _make_assertion("A", "linkedin"),
        ]
        result = resolver.resolve_field("field", assertions)
        assert len(result.all_assertions) == 3
        assert len(result.winning_assertions) == 2
        assert len(result.dissenting_assertions) == 1

    def test_winning_value_from_best_scored(self) -> None:
        """The winning value should be the exact string from the
        highest-scored assertion (preserving original casing)."""
        resolver = ConflictResolver()
        assertions = [
            _make_assertion(
                "openai", "crunchbase",
                grounding=0.99, trust=0.99,
            ),
            _make_assertion(
                "OpenAI", "techcrunch",
                grounding=0.50, trust=0.50,
            ),
        ]
        result = resolver.resolve_field("name", assertions)
        # Both normalize to "openai", so unanimous.
        # Winner should be the form from the best-scored assertion
        assert result.winning_value == "openai"
