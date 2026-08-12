"""Tests for graph/confidence.py — multi-signal confidence scoring."""
from __future__ import annotations

from provenmesh.graph.confidence import (
    ConfidenceFactors,
    compute_entity_confidence,
    compute_relationship_confidence,
)


class TestConfidenceFactors:
    def test_defaults(self) -> None:
        f = ConfidenceFactors()
        assert f.resolution_confidence == 0.0
        assert f.grounding_ratio == 0.0
        assert f.source_count == 1
        assert f.is_seed is False
        assert f.schema_valid is False
        assert f.days_since_last_update == 0


class TestComputeEntityConfidence:
    def test_seed_always_one(self) -> None:
        f = ConfidenceFactors(is_seed=True)
        assert compute_entity_confidence(f) == 1.0

    def test_seed_overrides_low_scores(self) -> None:
        f = ConfidenceFactors(
            is_seed=True,
            resolution_confidence=0.0,
            grounding_ratio=0.0,
        )
        assert compute_entity_confidence(f) == 1.0

    def test_perfect_scores(self) -> None:
        f = ConfidenceFactors(
            resolution_confidence=1.0,
            grounding_ratio=1.0,
            source_count=5,
            schema_valid=True,
            days_since_last_update=0,
        )
        score = compute_entity_confidence(f)
        assert score == 1.0

    def test_zero_scores(self) -> None:
        f = ConfidenceFactors(
            resolution_confidence=0.0,
            grounding_ratio=0.0,
            source_count=0,
            schema_valid=False,
            days_since_last_update=365,
        )
        score = compute_entity_confidence(f)
        assert score < 0.1

    def test_partial_scores(self) -> None:
        f = ConfidenceFactors(
            resolution_confidence=0.85,
            grounding_ratio=0.9,
            source_count=2,
            schema_valid=True,
            days_since_last_update=10,
        )
        score = compute_entity_confidence(f)
        assert 0.5 < score < 1.0

    def test_recency_decay_7_days(self) -> None:
        f = ConfidenceFactors(
            resolution_confidence=1.0, grounding_ratio=1.0,
            source_count=5, schema_valid=True,
            days_since_last_update=7,
        )
        assert compute_entity_confidence(f) == 1.0

    def test_recency_decay_30_days(self) -> None:
        f1 = ConfidenceFactors(
            resolution_confidence=1.0, grounding_ratio=1.0,
            source_count=5, schema_valid=True,
            days_since_last_update=7,
        )
        f2 = ConfidenceFactors(
            resolution_confidence=1.0, grounding_ratio=1.0,
            source_count=5, schema_valid=True,
            days_since_last_update=30,
        )
        assert compute_entity_confidence(f1) >= compute_entity_confidence(f2)

    def test_recency_decay_90_days(self) -> None:
        f = ConfidenceFactors(
            resolution_confidence=1.0, grounding_ratio=1.0,
            source_count=5, schema_valid=True,
            days_since_last_update=90,
        )
        score = compute_entity_confidence(f)
        assert score < 1.0

    def test_recency_decay_old(self) -> None:
        f = ConfidenceFactors(
            resolution_confidence=1.0, grounding_ratio=1.0,
            source_count=5, schema_valid=True,
            days_since_last_update=180,
        )
        score = compute_entity_confidence(f)
        assert score < 1.0

    def test_clamped_to_one(self) -> None:
        f = ConfidenceFactors(
            resolution_confidence=2.0,  # Over 1.0
            grounding_ratio=2.0,
        )
        score = compute_entity_confidence(f)
        assert score <= 1.0

    def test_multi_source_boost(self) -> None:
        f1 = ConfidenceFactors(
            resolution_confidence=0.8, grounding_ratio=0.8,
            source_count=1,
        )
        f5 = ConfidenceFactors(
            resolution_confidence=0.8, grounding_ratio=0.8,
            source_count=5,
        )
        assert compute_entity_confidence(f5) > compute_entity_confidence(f1)


class TestComputeRelationshipConfidence:
    def test_perfect(self) -> None:
        score = compute_relationship_confidence(1.0, 1.0, 1.0, True)
        assert score == 1.0

    def test_ungrounded_evidence(self) -> None:
        grounded = compute_relationship_confidence(1.0, 1.0, 1.0, True)
        ungrounded = compute_relationship_confidence(1.0, 1.0, 1.0, False)
        assert grounded > ungrounded

    def test_weakest_entity(self) -> None:
        score = compute_relationship_confidence(0.5, 1.0, 1.0, True)
        assert score < 1.0
        # Entity min should be 0.5, pulling score down
        assert score < 0.85

    def test_zero_scores(self) -> None:
        score = compute_relationship_confidence(0.0, 0.0, 0.0, False)
        assert score == 0.1  # Only evidence_factor * 0.2 = 0.5 * 0.2 = 0.1

    def test_clamping(self) -> None:
        score = compute_relationship_confidence(2.0, 2.0, 2.0, True)
        assert score <= 1.0
