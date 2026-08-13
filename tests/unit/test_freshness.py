"""Tests for data freshness monitor.

Covers:
    - FreshnessLevel classification
    - Per-record-type policies (STARTUP, NEWS, PAPER, etc.)
    - EntityFreshness assessment and serialization
    - RecrawlQueue building and priority sorting
    - Edge cases: no fetch date, future dates, naive datetime
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from provenmesh.crawler.freshness import (
    EntityFreshness,
    FreshnessLevel,
    FreshnessMonitor,
    FreshnessPolicy,
    RecrawlQueue,
)

NOW = datetime.now(tz=UTC)


class TestFreshnessLevel:
    def test_all_levels_exist(self) -> None:
        assert FreshnessLevel.FRESH == "fresh"
        assert FreshnessLevel.AGING == "aging"
        assert FreshnessLevel.STALE == "stale"
        assert FreshnessLevel.CRITICAL == "critical"


class TestFreshnessPolicy:
    def test_frozen(self) -> None:
        p = FreshnessPolicy(record_type="STARTUP", max_age_days=14)
        with pytest.raises(AttributeError):
            p.max_age_days = 30  # type: ignore[misc]

    def test_defaults(self) -> None:
        p = FreshnessPolicy(record_type="TEST", max_age_days=7)
        assert p.aging_threshold == 0.7
        assert p.critical_multiplier == 2.0


class TestEntityFreshness:
    def test_to_dict(self) -> None:
        ef = EntityFreshness(
            entity_id="e1",
            entity_name="OpenAI",
            record_type="STARTUP",
            level=FreshnessLevel.FRESH,
            freshness_score=95.0,
            last_fetched=NOW,
        )
        d = ef.to_dict()
        assert d["entity_id"] == "e1"
        assert d["level"] == "fresh"
        assert d["freshness_score"] == 95.0
        assert d["last_fetched"] is not None

    def test_to_dict_no_fetch(self) -> None:
        ef = EntityFreshness(entity_id="e1")
        d = ef.to_dict()
        assert d["last_fetched"] is None


class TestRecrawlQueue:
    def test_empty_queue(self) -> None:
        q = RecrawlQueue()
        assert not q.needs_action
        assert len(q.sorted_by_priority()) == 0

    def test_add_stale(self) -> None:
        q = RecrawlQueue()
        q.add(EntityFreshness(
            entity_id="e1", level=FreshnessLevel.STALE, priority=0.8,
        ))
        assert q.total_stale == 1
        assert q.needs_action

    def test_add_critical(self) -> None:
        q = RecrawlQueue()
        q.add(EntityFreshness(
            entity_id="e1", level=FreshnessLevel.CRITICAL, priority=1.0,
        ))
        assert q.total_critical == 1
        assert q.needs_action

    def test_add_aging(self) -> None:
        q = RecrawlQueue()
        q.add(EntityFreshness(
            entity_id="e1", level=FreshnessLevel.AGING, priority=0.5,
        ))
        assert q.total_aging == 1
        assert not q.needs_action  # Aging alone doesn't need action

    def test_sorted_by_priority(self) -> None:
        q = RecrawlQueue()
        q.add(EntityFreshness(
            entity_id="low", level=FreshnessLevel.AGING, priority=0.3,
        ))
        q.add(EntityFreshness(
            entity_id="high", level=FreshnessLevel.CRITICAL, priority=1.0,
        ))
        q.add(EntityFreshness(
            entity_id="mid", level=FreshnessLevel.STALE, priority=0.7,
        ))
        sorted_items = q.sorted_by_priority()
        assert sorted_items[0].entity_id == "high"
        assert sorted_items[1].entity_id == "mid"
        assert sorted_items[2].entity_id == "low"

    def test_to_dict(self) -> None:
        q = RecrawlQueue()
        q.add(EntityFreshness(
            entity_id="e1", level=FreshnessLevel.STALE, priority=0.8,
        ))
        d = q.to_dict()
        assert d["total_items"] == 1
        assert d["needs_action"] is True
        assert len(d["top_priority"]) == 1


class TestFreshnessMonitorAssess:
    def test_fresh_entity(self) -> None:
        monitor = FreshnessMonitor()
        result = monitor.assess_entity(
            entity_id="e1",
            record_type="STARTUP",
            last_fetched=NOW - timedelta(days=1),
        )
        assert result.level == FreshnessLevel.FRESH
        assert result.freshness_score > 80.0
        assert result.priority < 0.5

    def test_aging_entity(self) -> None:
        monitor = FreshnessMonitor()
        # STARTUP policy = 14 days, aging threshold = 0.7 * 14 = 9.8 days
        result = monitor.assess_entity(
            entity_id="e1",
            record_type="STARTUP",
            last_fetched=NOW - timedelta(days=11),
        )
        assert result.level == FreshnessLevel.AGING

    def test_stale_entity(self) -> None:
        monitor = FreshnessMonitor()
        # STARTUP policy = 14 days
        result = monitor.assess_entity(
            entity_id="e1",
            record_type="STARTUP",
            last_fetched=NOW - timedelta(days=16),
        )
        assert result.level == FreshnessLevel.STALE

    def test_critical_entity(self) -> None:
        monitor = FreshnessMonitor()
        # STARTUP critical = 14 * 2.0 = 28 days
        result = monitor.assess_entity(
            entity_id="e1",
            record_type="STARTUP",
            last_fetched=NOW - timedelta(days=30),
        )
        assert result.level == FreshnessLevel.CRITICAL

    def test_no_fetch_date_is_critical(self) -> None:
        monitor = FreshnessMonitor()
        result = monitor.assess_entity(
            entity_id="e1",
            record_type="STARTUP",
            last_fetched=None,
        )
        assert result.level == FreshnessLevel.CRITICAL
        assert result.freshness_score == 0.0
        assert result.priority == 1.0

    def test_news_goes_stale_fast(self) -> None:
        monitor = FreshnessMonitor()
        # NEWS policy = 1 day, 2 days old = critical (2x threshold)
        result = monitor.assess_entity(
            entity_id="e1",
            record_type="NEWS",
            last_fetched=NOW - timedelta(days=2),
        )
        assert result.level == FreshnessLevel.CRITICAL

    def test_paper_stays_fresh_long(self) -> None:
        monitor = FreshnessMonitor()
        # PAPER policy = 90 days
        result = monitor.assess_entity(
            entity_id="e1",
            record_type="PAPER",
            last_fetched=NOW - timedelta(days=30),
        )
        assert result.level == FreshnessLevel.FRESH

    def test_unknown_type_uses_fallback(self) -> None:
        monitor = FreshnessMonitor()
        result = monitor.assess_entity(
            entity_id="e1",
            record_type="UNKNOWN_TYPE",
            last_fetched=NOW - timedelta(days=35),
        )
        assert result.level == FreshnessLevel.STALE
        assert result.max_age_days == 30

    def test_custom_policy(self) -> None:
        monitor = FreshnessMonitor(policies={"STARTUP": 7})
        result = monitor.assess_entity(
            entity_id="e1",
            record_type="STARTUP",
            last_fetched=NOW - timedelta(days=8),
        )
        assert result.level == FreshnessLevel.STALE
        assert result.max_age_days == 7

    def test_naive_datetime(self) -> None:
        monitor = FreshnessMonitor()
        naive = datetime(2024, 1, 1)  # noqa: DTZ001
        result = monitor.assess_entity(
            entity_id="e1",
            record_type="STARTUP",
            last_fetched=naive,
        )
        assert result.level in (FreshnessLevel.STALE, FreshnessLevel.CRITICAL)

    def test_future_date_is_fresh(self) -> None:
        monitor = FreshnessMonitor()
        future = NOW + timedelta(hours=1)
        result = monitor.assess_entity(
            entity_id="e1",
            record_type="STARTUP",
            last_fetched=future,
        )
        assert result.level == FreshnessLevel.FRESH
        assert result.freshness_score == 100.0

    def test_freshness_score_decays(self) -> None:
        monitor = FreshnessMonitor()
        fresh = monitor.assess_entity(
            entity_id="e1",
            record_type="STARTUP",
            last_fetched=NOW - timedelta(days=1),
        )
        old = monitor.assess_entity(
            entity_id="e2",
            record_type="STARTUP",
            last_fetched=NOW - timedelta(days=13),
        )
        assert fresh.freshness_score > old.freshness_score

    def test_priority_increases_with_age(self) -> None:
        monitor = FreshnessMonitor()
        fresh = monitor.assess_entity(
            entity_id="e1",
            record_type="STARTUP",
            last_fetched=NOW - timedelta(days=1),
        )
        old = monitor.assess_entity(
            entity_id="e2",
            record_type="STARTUP",
            last_fetched=NOW - timedelta(days=13),
        )
        assert fresh.priority < old.priority


class TestBuildRecrawlQueue:
    def test_mixed_entities(self) -> None:
        monitor = FreshnessMonitor()
        entities = [
            {
                "entity_id": "fresh",
                "record_type": "STARTUP",
                "last_fetched": NOW - timedelta(days=1),
                "entity_name": "FreshCo",
            },
            {
                "entity_id": "stale",
                "record_type": "STARTUP",
                "last_fetched": NOW - timedelta(days=20),
                "entity_name": "StaleCo",
            },
            {
                "entity_id": "critical",
                "record_type": "NEWS",
                "last_fetched": NOW - timedelta(days=5),
                "entity_name": "OldNews",
            },
        ]
        queue = monitor.build_recrawl_queue(entities)
        # Fresh entity should NOT be in queue
        ids = [item.entity_id for item in queue.items]
        assert "fresh" not in ids
        assert "stale" in ids
        assert "critical" in ids
        assert queue.needs_action

    def test_all_fresh(self) -> None:
        monitor = FreshnessMonitor()
        entities = [
            {
                "entity_id": "e1",
                "record_type": "PAPER",
                "last_fetched": NOW - timedelta(days=10),
            },
        ]
        queue = monitor.build_recrawl_queue(entities)
        assert len(queue.items) == 0
        assert not queue.needs_action

    def test_empty_input(self) -> None:
        monitor = FreshnessMonitor()
        queue = monitor.build_recrawl_queue([])
        assert len(queue.items) == 0

    def test_missing_fields_handled(self) -> None:
        monitor = FreshnessMonitor()
        queue = monitor.build_recrawl_queue([
            {"entity_id": "e1", "record_type": "STARTUP"},
        ])
        assert len(queue.items) == 1  # No fetch date = critical
        assert queue.total_critical == 1
