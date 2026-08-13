"""Data freshness monitor — automated staleness detection and re-crawl scheduling.

Tracks the age of every entity's data and determines which entities
need re-crawling based on configurable freshness policies per record type.

Key capabilities:
    - Per-record-type freshness policies (startups need fresher data than papers)
    - Staleness scoring with exponential decay
    - Priority queue for re-crawl scheduling (stalest entities first)
    - Change detection: flag entities whose source data likely changed
    - Freshness dashboard stats for monitoring
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum

from provenmesh.observability.logging import get_logger

logger = get_logger(__name__)


class FreshnessLevel(StrEnum):
    """How fresh the entity's data is."""

    FRESH = "fresh"           # Within policy window
    AGING = "aging"           # Approaching staleness
    STALE = "stale"           # Past policy window
    CRITICAL = "critical"     # Way past policy, needs urgent re-crawl


# ─── Default freshness policies (days) ────────────────────────────

_DEFAULT_POLICIES: dict[str, int] = {
    "STARTUP": 14,     # Startups change fast (funding rounds, etc.)
    "PRODUCT": 30,     # Products update monthly
    "NEWS": 1,         # News goes stale in a day
    "JOB": 7,          # Job listings change weekly
    "PAPER": 90,       # Academic papers are stable
}

_FALLBACK_POLICY_DAYS = 30


@dataclass(frozen=True)
class FreshnessPolicy:
    """Freshness policy for a record type."""

    record_type: str
    max_age_days: int
    aging_threshold: float = 0.7    # % of max_age before "aging"
    critical_multiplier: float = 2.0  # 2x max_age = critical


@dataclass
class EntityFreshness:
    """Freshness assessment for a single entity."""

    entity_id: str
    entity_name: str = ""
    record_type: str = ""
    source_url: str = ""

    # Timing
    last_fetched: datetime | None = None
    age_days: float = 0.0

    # Assessment
    level: FreshnessLevel = FreshnessLevel.FRESH
    freshness_score: float = 100.0    # 0-100
    priority: float = 0.0             # Re-crawl priority (higher = sooner)

    # Policy context
    max_age_days: int = 30
    days_until_stale: float = 0.0

    def to_dict(self) -> dict:
        return {
            "entity_id": self.entity_id,
            "entity_name": self.entity_name,
            "record_type": self.record_type,
            "source_url": self.source_url,
            "last_fetched": (
                self.last_fetched.isoformat()
                if self.last_fetched else None
            ),
            "age_days": round(self.age_days, 1),
            "level": self.level.value,
            "freshness_score": round(self.freshness_score, 1),
            "priority": round(self.priority, 3),
            "max_age_days": self.max_age_days,
            "days_until_stale": round(self.days_until_stale, 1),
        }


@dataclass
class RecrawlQueue:
    """Prioritized queue of entities that need re-crawling."""

    items: list[EntityFreshness] = field(default_factory=list)
    total_stale: int = 0
    total_critical: int = 0
    total_aging: int = 0

    def add(self, item: EntityFreshness) -> None:
        """Add entity and keep sorted by priority (highest first)."""
        self.items.append(item)
        if item.level == FreshnessLevel.STALE:
            self.total_stale += 1
        elif item.level == FreshnessLevel.CRITICAL:
            self.total_critical += 1
        elif item.level == FreshnessLevel.AGING:
            self.total_aging += 1

    def sorted_by_priority(self) -> list[EntityFreshness]:
        """Return items sorted by re-crawl priority (highest first)."""
        return sorted(
            self.items, key=lambda x: x.priority, reverse=True,
        )

    @property
    def needs_action(self) -> bool:
        return self.total_stale > 0 or self.total_critical > 0

    def to_dict(self) -> dict:
        return {
            "total_items": len(self.items),
            "total_stale": self.total_stale,
            "total_critical": self.total_critical,
            "total_aging": self.total_aging,
            "needs_action": self.needs_action,
            "top_priority": [
                item.to_dict()
                for item in self.sorted_by_priority()[:20]
            ],
        }


class FreshnessMonitor:
    """Monitors data freshness and schedules re-crawls.

    Evaluates entity staleness against configurable per-record-type
    policies and builds a prioritized re-crawl queue.
    """

    def __init__(
        self,
        policies: dict[str, int] | None = None,
    ) -> None:
        raw = {**_DEFAULT_POLICIES, **(policies or {})}
        self._policies: dict[str, FreshnessPolicy] = {
            rt: FreshnessPolicy(record_type=rt, max_age_days=days)
            for rt, days in raw.items()
        }

    def assess_entity(
        self,
        entity_id: str,
        record_type: str,
        last_fetched: datetime | None = None,
        entity_name: str = "",
        source_url: str = "",
    ) -> EntityFreshness:
        """Assess the freshness of a single entity."""
        policy = self._get_policy(record_type)

        if last_fetched is None:
            return EntityFreshness(
                entity_id=entity_id,
                entity_name=entity_name,
                record_type=record_type,
                source_url=source_url,
                level=FreshnessLevel.CRITICAL,
                freshness_score=0.0,
                priority=1.0,
                max_age_days=policy.max_age_days,
                days_until_stale=0.0,
            )

        now = datetime.now(tz=UTC)
        if last_fetched.tzinfo is None:
            last_fetched = last_fetched.replace(tzinfo=UTC)

        age_days = max(0.0, (now - last_fetched).total_seconds() / 86400.0)
        max_age = policy.max_age_days

        # Freshness score: exponential decay
        freshness_score = max(
            0.0,
            100.0 * math.pow(2, -age_days / max_age),
        )

        # Determine level
        level = self._classify_level(age_days, policy)

        # Re-crawl priority (0-1, higher = more urgent)
        priority = min(1.0, age_days / max_age)

        days_until_stale = max(0.0, max_age - age_days)

        result = EntityFreshness(
            entity_id=entity_id,
            entity_name=entity_name,
            record_type=record_type,
            source_url=source_url,
            last_fetched=last_fetched,
            age_days=age_days,
            level=level,
            freshness_score=freshness_score,
            priority=priority,
            max_age_days=max_age,
            days_until_stale=days_until_stale,
        )

        if level in (FreshnessLevel.STALE, FreshnessLevel.CRITICAL):
            logger.info(
                "entity_stale",
                entity_id=entity_id,
                level=level.value,
                age_days=round(age_days, 1),
                max_age=max_age,
            )

        return result

    def build_recrawl_queue(
        self,
        entities: list[dict],
    ) -> RecrawlQueue:
        """Build a prioritized re-crawl queue from entity metadata.

        Args:
            entities: list of dicts with keys:
                entity_id, record_type, last_fetched, entity_name, source_url
        """
        queue = RecrawlQueue()

        for entity in entities:
            assessment = self.assess_entity(
                entity_id=entity.get("entity_id", ""),
                record_type=entity.get("record_type", ""),
                last_fetched=entity.get("last_fetched"),
                entity_name=entity.get("entity_name", ""),
                source_url=entity.get("source_url", ""),
            )

            if assessment.level != FreshnessLevel.FRESH:
                queue.add(assessment)

        if queue.needs_action:
            logger.info(
                "recrawl_queue_built",
                total=len(queue.items),
                stale=queue.total_stale,
                critical=queue.total_critical,
            )

        return queue

    def _get_policy(self, record_type: str) -> FreshnessPolicy:
        """Get freshness policy for a record type."""
        key = record_type.upper()
        if key in self._policies:
            return self._policies[key]
        return FreshnessPolicy(
            record_type=key,
            max_age_days=_FALLBACK_POLICY_DAYS,
        )

    @staticmethod
    def _classify_level(
        age_days: float,
        policy: FreshnessPolicy,
    ) -> FreshnessLevel:
        """Classify freshness level based on age and policy."""
        max_age = policy.max_age_days
        critical_threshold = max_age * policy.critical_multiplier
        aging_threshold = max_age * policy.aging_threshold

        if age_days >= critical_threshold:
            return FreshnessLevel.CRITICAL
        if age_days >= max_age:
            return FreshnessLevel.STALE
        if age_days >= aging_threshold:
            return FreshnessLevel.AGING
        return FreshnessLevel.FRESH
