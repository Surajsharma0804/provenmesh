"""Data quality scoring engine — unified quality score per entity.

Produces a single 0-100 quality score for every entity by combining
signals from all pipeline stages:

    - Source diversity (multi-source vs single-source)
    - Grounding strength (fuzzy match quality)
    - Hallucination risk (trust score from detector)
    - Conflict consensus (agreement ratio)
    - Completeness (fields present vs required)
    - Freshness (data recency)

The quality score drives:
    1. Export gating: entities below threshold are held back
    2. Priority review: low-quality entities go to human review
    3. Dashboard reporting: stakeholders see quality distribution
    4. Re-crawl scheduling: stale or low-quality entities first
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum

from provenmesh.observability.logging import get_logger

logger = get_logger(__name__)


class QualityGrade(StrEnum):
    """Letter grade for entity quality."""

    A = "A"    # 90-100: Excellent, auto-export
    B = "B"    # 75-89: Good, auto-export
    C = "C"    # 60-74: Fair, flag for review
    D = "D"    # 40-59: Poor, needs re-crawl
    F = "F"    # 0-39: Failing, block export

    @classmethod
    def from_score(cls, score: float) -> QualityGrade:
        """Convert numeric score to letter grade."""
        if score >= 90:
            return cls.A
        if score >= 75:
            return cls.B
        if score >= 60:
            return cls.C
        if score >= 40:
            return cls.D
        return cls.F


@dataclass
class QualityDimension:
    """Score for a single quality dimension."""

    name: str
    score: float         # 0-100
    weight: float        # 0-1 contribution to total
    details: str = ""

    @property
    def weighted_score(self) -> float:
        return self.score * self.weight


@dataclass
class QualityReport:
    """Complete quality assessment for an entity."""

    entity_id: str
    entity_name: str = ""
    record_type: str = ""

    # Overall score (0-100)
    overall_score: float = 0.0
    grade: QualityGrade = QualityGrade.F

    # Individual dimensions
    dimensions: list[QualityDimension] = field(default_factory=list)

    # Actionable recommendations
    recommendations: list[str] = field(default_factory=list)

    # Decision
    export_allowed: bool = False
    needs_review: bool = False
    needs_recrawl: bool = False

    scored_at: datetime = field(
        default_factory=lambda: datetime.now(tz=UTC),
    )

    def to_dict(self) -> dict:
        return {
            "entity_id": self.entity_id,
            "entity_name": self.entity_name,
            "record_type": self.record_type,
            "overall_score": round(self.overall_score, 1),
            "grade": self.grade.value,
            "export_allowed": self.export_allowed,
            "needs_review": self.needs_review,
            "needs_recrawl": self.needs_recrawl,
            "dimensions": [
                {
                    "name": d.name,
                    "score": round(d.score, 1),
                    "weight": round(d.weight, 2),
                    "weighted_score": round(d.weighted_score, 1),
                    "details": d.details,
                }
                for d in self.dimensions
            ],
            "recommendations": self.recommendations,
            "scored_at": self.scored_at.isoformat(),
        }


# ─── Default weights (must sum to 1.0) ───────────────────────────

_DEFAULT_WEIGHTS = {
    "source_diversity": 0.15,
    "grounding_strength": 0.25,
    "hallucination_risk": 0.25,
    "conflict_consensus": 0.15,
    "completeness": 0.10,
    "freshness": 0.10,
}

# Export threshold (0-100)
_EXPORT_THRESHOLD = 60.0
_REVIEW_THRESHOLD = 75.0

# Freshness half-life in days
_FRESHNESS_HALF_LIFE = 30.0


class QualityScorer:
    """Computes unified quality scores for entities.

    Combines multiple quality signals into a single 0-100 score
    with letter grading, export gating, and actionable recommendations.
    """

    def __init__(
        self,
        weights: dict[str, float] | None = None,
        export_threshold: float = _EXPORT_THRESHOLD,
        review_threshold: float = _REVIEW_THRESHOLD,
    ) -> None:
        self._weights = weights or _DEFAULT_WEIGHTS.copy()
        self._export_threshold = export_threshold
        self._review_threshold = review_threshold

    def score_entity(
        self,
        entity_id: str,
        entity_name: str = "",
        record_type: str = "",
        source_count: int = 0,
        grounding_scores: list[float] | None = None,
        trust_score: float = 1.0,
        consensus_ratio: float = 1.0,
        fields_present: int = 0,
        fields_required: int = 0,
        latest_fetch: datetime | None = None,
    ) -> QualityReport:
        """Score a single entity across all quality dimensions.

        All inputs are optional — the scorer degrades gracefully
        when information is missing (scores 0 for that dimension).
        """
        dims: list[QualityDimension] = []

        # 1. Source diversity
        div_score = self._score_source_diversity(source_count)
        dims.append(QualityDimension(
            name="source_diversity",
            score=div_score,
            weight=self._weights.get("source_diversity", 0.15),
            details=f"{source_count} source(s)",
        ))

        # 2. Grounding strength
        grounding = grounding_scores or []
        grnd_score = self._score_grounding(grounding)
        dims.append(QualityDimension(
            name="grounding_strength",
            score=grnd_score,
            weight=self._weights.get("grounding_strength", 0.25),
            details=(
                f"avg={sum(grounding) / len(grounding):.2f}"
                if grounding else "no grounding data"
            ),
        ))

        # 3. Hallucination risk (inverted: low trust = low score)
        hal_score = trust_score * 100.0
        dims.append(QualityDimension(
            name="hallucination_risk",
            score=hal_score,
            weight=self._weights.get("hallucination_risk", 0.25),
            details=f"trust={trust_score:.2f}",
        ))

        # 4. Conflict consensus
        cons_score = consensus_ratio * 100.0
        dims.append(QualityDimension(
            name="conflict_consensus",
            score=cons_score,
            weight=self._weights.get("conflict_consensus", 0.15),
            details=f"consensus={consensus_ratio:.2f}",
        ))

        # 5. Completeness
        comp_score = self._score_completeness(
            fields_present, fields_required,
        )
        dims.append(QualityDimension(
            name="completeness",
            score=comp_score,
            weight=self._weights.get("completeness", 0.10),
            details=f"{fields_present}/{fields_required} fields",
        ))

        # 6. Freshness
        fresh_score = self._score_freshness(latest_fetch)
        dims.append(QualityDimension(
            name="freshness",
            score=fresh_score,
            weight=self._weights.get("freshness", 0.10),
            details=(
                f"fetched {self._age_description(latest_fetch)}"
                if latest_fetch else "no fetch data"
            ),
        ))

        # Calculate overall score
        overall = sum(d.weighted_score for d in dims)
        grade = QualityGrade.from_score(overall)

        # Generate recommendations
        recommendations = self._generate_recommendations(dims, overall)

        report = QualityReport(
            entity_id=entity_id,
            entity_name=entity_name,
            record_type=record_type,
            overall_score=overall,
            grade=grade,
            dimensions=dims,
            recommendations=recommendations,
            export_allowed=overall >= self._export_threshold,
            needs_review=(
                self._export_threshold
                <= overall
                < self._review_threshold
            ),
            needs_recrawl=any(
                d.score < 40 and d.name in (
                    "source_diversity", "freshness", "grounding_strength",
                )
                for d in dims
            ),
        )

        logger.info(
            "quality_score_computed",
            entity_id=entity_id,
            score=round(overall, 1),
            grade=grade.value,
            export=report.export_allowed,
        )

        return report

    @staticmethod
    def _score_source_diversity(count: int) -> float:
        """More sources = higher confidence in data accuracy.

        1 source:  40 (can't cross-verify)
        2 sources: 70
        3 sources: 85
        4+ sources: 95-100 (diminishing returns)
        """
        if count <= 0:
            return 0.0
        if count == 1:
            return 40.0
        if count == 2:
            return 70.0
        # Logarithmic growth after 3 sources
        return min(100.0, 85.0 + 15.0 * math.log2(count - 2))

    @staticmethod
    def _score_grounding(scores: list[float]) -> float:
        """Average grounding score scaled to 0-100.

        Scores might be 0-1 (normalized) or 0-100 (raw fuzzy).
        We detect and handle both.
        """
        if not scores:
            return 0.0

        avg = sum(scores) / len(scores)

        # Auto-detect scale
        if avg <= 1.0:
            return avg * 100.0
        return min(100.0, avg)

    @staticmethod
    def _score_completeness(present: int, required: int) -> float:
        """Percentage of required fields that are populated."""
        if required <= 0:
            return 100.0  # No requirements = fully complete
        return min(100.0, (present / required) * 100.0)

    def _score_freshness(self, latest_fetch: datetime | None) -> float:
        """Exponential decay based on data age.

        Fresh data (today): 100
        30 days old: 50
        60 days old: 25
        Very old: minimum 10
        """
        if latest_fetch is None:
            return 0.0

        now = datetime.now(tz=UTC)

        if latest_fetch.tzinfo is None:
            latest_fetch = latest_fetch.replace(tzinfo=UTC)

        age_days = (now - latest_fetch).total_seconds() / 86400.0

        if age_days <= 0:
            return 100.0

        decay = math.pow(2, -age_days / _FRESHNESS_HALF_LIFE)
        return max(10.0, decay * 100.0)

    @staticmethod
    def _age_description(dt: datetime | None) -> str:
        """Human-readable age description."""
        if dt is None:
            return "unknown"

        now = datetime.now(tz=UTC)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)

        days = (now - dt).days

        if days == 0:
            return "today"
        if days == 1:
            return "1 day ago"
        if days < 30:
            return f"{days} days ago"
        if days < 365:
            months = days // 30
            return f"{months} month(s) ago"
        years = days // 365
        return f"{years} year(s) ago"

    @staticmethod
    def _generate_recommendations(
        dims: list[QualityDimension],
        overall: float,
    ) -> list[str]:
        """Generate actionable recommendations based on weak dimensions."""
        recs: list[str] = []

        for d in dims:
            if d.score < 40:
                if d.name == "source_diversity":
                    recs.append(
                        "Add more data sources to cross-verify "
                        "this entity's information.",
                    )
                elif d.name == "grounding_strength":
                    recs.append(
                        "Re-extract with stricter evidence requirements "
                        "— current grounding is weak.",
                    )
                elif d.name == "hallucination_risk":
                    recs.append(
                        "High hallucination risk detected. Manual review "
                        "recommended before export.",
                    )
                elif d.name == "freshness":
                    recs.append(
                        "Data is stale. Schedule a re-crawl to get "
                        "up-to-date information.",
                    )
                elif d.name == "completeness":
                    recs.append(
                        "Many required fields are missing. Consider "
                        "additional sources or manual enrichment.",
                    )
                elif d.name == "conflict_consensus":
                    recs.append(
                        "Sources disagree on key fields. Human review "
                        "needed to resolve conflicts.",
                    )

        if not recs and overall >= 90:
            recs.append("Excellent data quality. Ready for export.")

        return recs
