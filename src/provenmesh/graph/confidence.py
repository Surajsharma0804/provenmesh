"""Confidence scoring — multi-signal confidence aggregation (v2 §26).

Combines resolution confidence, grounding ratio, source count, and
recency to produce a final entity confidence score.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from provenmesh.observability.logging import get_logger

logger = get_logger(__name__)


@dataclass
class ConfidenceFactors:
    """Individual factors contributing to entity confidence."""

    resolution_confidence: float = 0.0
    grounding_ratio: float = 0.0
    source_count: int = 1
    is_seed: bool = False
    schema_valid: bool = False
    days_since_last_update: int = 0


def compute_entity_confidence(factors: ConfidenceFactors) -> float:
    """Compute an overall confidence score for an entity.

    Weighted aggregation:
        - Resolution quality: 30%
        - Grounding ratio: 30%
        - Multi-source corroboration: 20%
        - Schema validity: 10%
        - Recency: 10%

    Seed entities get a 1.0 floor.
    """
    if factors.is_seed:
        return 1.0

    # Resolution quality (0-1)
    resolution_score = min(factors.resolution_confidence, 1.0)

    # Grounding ratio (0-1)
    grounding_score = min(factors.grounding_ratio, 1.0)

    # Multi-source corroboration: log scale, caps at 5 sources
    source_score = min(factors.source_count / 5.0, 1.0)

    # Schema validity (binary)
    schema_score = 1.0 if factors.schema_valid else 0.0

    # Recency: decays over 90 days
    if factors.days_since_last_update <= 7:
        recency_score = 1.0
    elif factors.days_since_last_update <= 30:
        recency_score = 0.8
    elif factors.days_since_last_update <= 90:
        recency_score = 0.5
    else:
        recency_score = 0.2

    # Weighted aggregation
    confidence = (
        0.30 * resolution_score
        + 0.30 * grounding_score
        + 0.20 * source_score
        + 0.10 * schema_score
        + 0.10 * recency_score
    )

    return round(min(max(confidence, 0.0), 1.0), 4)


def compute_relationship_confidence(
    entity_a_confidence: float,
    entity_b_confidence: float,
    extraction_confidence: float,
    evidence_grounded: bool,
) -> float:
    """Compute confidence for a relationship edge.

    A relationship is only as strong as its weakest entity.
    """
    entity_min = min(entity_a_confidence, entity_b_confidence)
    evidence_factor = 1.0 if evidence_grounded else 0.5

    confidence = (
        0.40 * entity_min
        + 0.40 * extraction_confidence
        + 0.20 * evidence_factor
    )

    return round(min(max(confidence, 0.0), 1.0), 4)
