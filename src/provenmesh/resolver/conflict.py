"""Multi-source conflict resolution with evidence-weighted voting.

When the same entity is crawled from multiple sources, fields may disagree.
This module resolves conflicts using a weighted voting algorithm:

    score = grounding_quality * trust_score * recency_decay * source_credibility

The winner is the value with the highest aggregate score across all sources
that assert it. A full dissent audit trail is preserved so analysts can
review why a particular value was chosen.

Example:
    Crunchbase says Founded=2015 (grounding=95%, trust=0.97, 2 days old)
    TechCrunch  says Founded=2015 (grounding=92%, trust=0.95, 5 days old)
    VentureBeat says Founded=2016 (grounding=88%, trust=0.80, 30 days old)

    → "2015" wins: 2 sources agree, higher evidence quality
    → Confidence: 0.94
    → Dissent: VentureBeat (lower credibility, single source)
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import UTC, datetime

from provenmesh.observability.logging import get_logger

logger = get_logger(__name__)

# ─── Recency decay configuration ─────────────────────────────────

# Half-life in days: after this many days, a source's recency
# weight drops to 50%. Fresher data is more trustworthy.
_RECENCY_HALF_LIFE_DAYS = 30.0

# Minimum recency weight (even very old data gets some credit)
_MIN_RECENCY_WEIGHT = 0.1

# Minimum number of sources to consider a field "well-sourced"
_WELL_SOURCED_THRESHOLD = 3

# Source credibility defaults (can be overridden per-source)
_DEFAULT_SOURCE_CREDIBILITY: dict[str, float] = {
    "crunchbase": 0.95,
    "pitchbook": 0.93,
    "linkedin": 0.90,
    "techcrunch": 0.88,
    "producthunt": 0.85,
    "github": 0.92,
    "arxiv": 0.95,
    "ycombinator": 0.90,
}

_FALLBACK_CREDIBILITY = 0.75


@dataclass(frozen=True)
class SourceAssertion:
    """A single source's claim about a field value.

    Captures everything needed to score this assertion:
    the value itself, where it came from, and how trustworthy
    the extraction was.
    """

    value: str
    source_url: str
    source_name: str = ""
    grounding_score: float = 0.0    # 0-1, from grounding engine
    trust_score: float = 1.0        # 0-1, from hallucination detector
    llm_confidence: float = 0.0     # 0-1, from LLM extraction
    fetched_at: datetime = field(
        default_factory=lambda: datetime.now(tz=UTC),
    )
    evidence_text: str = ""


@dataclass
class FieldResolution:
    """Resolution result for a single field across multiple sources.

    Contains the winning value, confidence score, and the full
    audit trail of all assertions (including dissenting ones).
    """

    field_name: str
    winning_value: str
    confidence: float = 0.0
    source_count: int = 0
    agreeing_sources: int = 0
    consensus_ratio: float = 0.0     # agreeing / total

    # Audit trail
    all_assertions: list[SourceAssertion] = field(default_factory=list)
    winning_assertions: list[SourceAssertion] = field(default_factory=list)
    dissenting_assertions: list[SourceAssertion] = field(
        default_factory=list,
    )

    # Resolution metadata
    resolution_method: str = ""      # unanimous, majority, quality_winner
    is_contested: bool = False

    @property
    def dissent_summary(self) -> str:
        """Human-readable summary of disagreements."""
        if not self.dissenting_assertions:
            return ""
        dissenters = [
            f"{a.source_name or a.source_url}: '{a.value}'"
            for a in self.dissenting_assertions
        ]
        return f"Disagree: {', '.join(dissenters)}"


@dataclass
class ConflictReport:
    """Complete conflict resolution report for an entity record.

    Aggregates per-field resolutions and provides an overall
    consensus score for the entire record.
    """

    entity_id: str = ""
    field_resolutions: dict[str, FieldResolution] = field(
        default_factory=dict,
    )
    overall_consensus: float = 0.0
    contested_fields: list[str] = field(default_factory=list)
    total_fields: int = 0
    unanimous_fields: int = 0

    @property
    def has_conflicts(self) -> bool:
        return len(self.contested_fields) > 0

    @property
    def consensus_ratio(self) -> float:
        if self.total_fields == 0:
            return 0.0
        return self.unanimous_fields / self.total_fields

    def get_winning_values(self) -> dict[str, str]:
        """Extract field_name → winning_value map for merging."""
        return {
            name: res.winning_value
            for name, res in self.field_resolutions.items()
        }


class ConflictResolver:
    """Evidence-weighted multi-source conflict resolution.

    Resolves disagreements between sources using a scoring algorithm
    that considers: evidence quality, hallucination trust, data recency,
    source credibility, and multi-source consensus.
    """

    def __init__(
        self,
        source_credibility: dict[str, float] | None = None,
        recency_half_life_days: float = _RECENCY_HALF_LIFE_DAYS,
    ) -> None:
        self._credibility = {
            **_DEFAULT_SOURCE_CREDIBILITY,
            **(source_credibility or {}),
        }
        self._half_life = recency_half_life_days

    def resolve_record(
        self,
        field_assertions: dict[str, list[SourceAssertion]],
        entity_id: str = "",
    ) -> ConflictReport:
        """Resolve all field conflicts for a single entity.

        Args:
            field_assertions: {field_name: [SourceAssertion, ...]}
            entity_id: Optional entity identifier for logging

        Returns:
            ConflictReport with per-field resolutions
        """
        report = ConflictReport(entity_id=entity_id)

        for field_name, assertions in field_assertions.items():
            if not assertions:
                continue

            resolution = self.resolve_field(field_name, assertions)
            report.field_resolutions[field_name] = resolution
            report.total_fields += 1

            if resolution.is_contested:
                report.contested_fields.append(field_name)
            else:
                report.unanimous_fields += 1

        # Overall consensus score
        if report.total_fields > 0:
            confidences = [
                r.confidence
                for r in report.field_resolutions.values()
            ]
            report.overall_consensus = sum(confidences) / len(confidences)

        if report.has_conflicts:
            logger.info(
                "conflict_resolution_complete",
                entity_id=entity_id,
                total_fields=report.total_fields,
                contested=len(report.contested_fields),
                consensus=round(report.overall_consensus, 3),
            )

        return report

    def resolve_field(
        self,
        field_name: str,
        assertions: list[SourceAssertion],
    ) -> FieldResolution:
        """Resolve a single field using evidence-weighted voting.

        Algorithm:
            1. Normalize values for comparison (lowercase, strip)
            2. Group assertions by normalized value
            3. Score each group: sum of individual assertion scores
            4. Winner = group with highest aggregate score
            5. Calculate confidence from winner's score share

        Args:
            field_name: Name of the field being resolved
            assertions: All source assertions for this field

        Returns:
            FieldResolution with winner and audit trail
        """
        if len(assertions) == 1:
            return self._single_source_resolution(
                field_name, assertions[0],
            )

        # Score each assertion individually
        scored: list[tuple[SourceAssertion, float]] = [
            (a, self._score_assertion(a))
            for a in assertions
        ]

        # Group by normalized value
        value_groups: dict[str, list[tuple[SourceAssertion, float]]] = {}
        for assertion, score in scored:
            key = self._normalize_value(assertion.value)
            value_groups.setdefault(key, []).append((assertion, score))

        # Find the winning group (highest aggregate score)
        best_key = ""
        best_score = -1.0
        for key, group in value_groups.items():
            group_score = sum(s for _, s in group)
            if group_score > best_score:
                best_score = group_score
                best_key = key

        winning_group = value_groups[best_key]
        total_score = sum(s for _, s in scored)

        # Build resolution
        winning_assertions = [a for a, _ in winning_group]
        dissenting_assertions = [
            a for a, _ in scored
            if self._normalize_value(a.value) != best_key
        ]

        # Use the original (non-normalized) value from the highest-
        # scored assertion in the winning group
        best_assertion = max(winning_group, key=lambda x: x[1])
        winning_value = best_assertion[0].value

        # Confidence = winner's share of total score * quality factor
        score_share = best_score / total_score if total_score > 0 else 0.0
        quality_factor = best_assertion[1]  # Best individual score
        confidence = min(1.0, score_share * (0.5 + 0.5 * quality_factor))

        # Determine resolution method
        if len(value_groups) == 1:
            method = "unanimous"
        elif len(winning_group) > len(assertions) / 2:
            method = "majority_vote"
        else:
            method = "quality_winner"

        return FieldResolution(
            field_name=field_name,
            winning_value=winning_value,
            confidence=round(confidence, 4),
            source_count=len(assertions),
            agreeing_sources=len(winning_group),
            consensus_ratio=round(
                len(winning_group) / len(assertions), 3,
            ),
            all_assertions=assertions,
            winning_assertions=winning_assertions,
            dissenting_assertions=dissenting_assertions,
            resolution_method=method,
            is_contested=len(value_groups) > 1,
        )

    def _score_assertion(self, assertion: SourceAssertion) -> float:
        """Score a single assertion using the evidence-weighted formula.

        score = grounding * trust * recency * credibility

        Each factor is 0-1, so the final score is also 0-1.
        """
        grounding = assertion.grounding_score
        trust = assertion.trust_score
        recency = self._recency_weight(assertion.fetched_at)
        credibility = self._source_credibility(assertion.source_name)

        return grounding * trust * recency * credibility

    def _recency_weight(self, fetched_at: datetime) -> float:
        """Exponential decay weight based on data age.

        Uses half-life decay: weight = 2^(-age/half_life)
        So data that is half_life days old gets weight 0.5,
        2x half_life gets 0.25, etc.
        """
        now = datetime.now(tz=UTC)

        # Handle naive datetimes
        if fetched_at.tzinfo is None:
            fetched_at = fetched_at.replace(tzinfo=UTC)

        age_days = (now - fetched_at).total_seconds() / 86400.0

        if age_days <= 0:
            return 1.0

        decay = math.pow(2, -age_days / self._half_life)
        return max(_MIN_RECENCY_WEIGHT, decay)

    def _source_credibility(self, source_name: str) -> float:
        """Look up source credibility score.

        Known sources (Crunchbase, PitchBook, etc.) have curated
        credibility scores. Unknown sources get a conservative default.
        """
        if not source_name:
            return _FALLBACK_CREDIBILITY

        return self._credibility.get(
            source_name.lower().strip(),
            _FALLBACK_CREDIBILITY,
        )

    @staticmethod
    def _normalize_value(value: str) -> str:
        """Normalize a value for comparison.

        Strips whitespace, lowercases, removes common noise characters.
        Two values that normalize to the same string are considered
        'the same assertion'.
        """
        return " ".join(value.lower().strip().split())

    @staticmethod
    def _single_source_resolution(
        field_name: str,
        assertion: SourceAssertion,
    ) -> FieldResolution:
        """Handle the trivial case: only one source for a field.

        Confidence is capped at 0.7 because single-source data
        can't be cross-verified.
        """
        base_confidence = min(
            assertion.grounding_score * assertion.trust_score,
            0.7,
        )
        return FieldResolution(
            field_name=field_name,
            winning_value=assertion.value,
            confidence=round(base_confidence, 4),
            source_count=1,
            agreeing_sources=1,
            consensus_ratio=1.0,
            all_assertions=[assertion],
            winning_assertions=[assertion],
            dissenting_assertions=[],
            resolution_method="single_source",
            is_contested=False,
        )
