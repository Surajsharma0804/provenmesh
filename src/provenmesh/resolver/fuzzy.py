"""Fuzzy matching — RapidFuzz-based entity matching (v2 §23).

Uses token_sort_ratio for order-insensitive matching:
    "Sam Altman" vs "Altman, Sam" → high score
"""

from __future__ import annotations

from dataclasses import dataclass

from rapidfuzz import fuzz, process

from provenmesh.observability.logging import get_logger

logger = get_logger(__name__)

DEFAULT_FUZZY_THRESHOLD = 85


@dataclass(frozen=True)
class FuzzyMatch:
    """Result of a fuzzy match attempt."""

    matched_name: str
    canonical_id: str
    score: float
    method: str = "fuzzy"


def fuzzy_match_single(
    query: str,
    candidate_name: str,
    threshold: float = DEFAULT_FUZZY_THRESHOLD,
) -> float:
    """Compare two names using token_sort_ratio.

    token_sort_ratio handles word reordering:
        "OpenAI Inc" vs "Inc OpenAI" → 100
    """
    return fuzz.token_sort_ratio(query.lower(), candidate_name.lower())


def fuzzy_match_batch(
    query: str,
    candidates: dict[str, str],
    threshold: float = DEFAULT_FUZZY_THRESHOLD,
    limit: int = 5,
) -> list[FuzzyMatch]:
    """Match a query against a batch of candidates.

    Args:
        query: The entity name to match
        candidates: Dict of {canonical_id: canonical_name}
        threshold: Minimum score to include (0-100)
        limit: Maximum results to return

    Returns:
        List of FuzzyMatch results, sorted by score descending
    """
    if not query or not candidates:
        return []

    # Build choices dict for RapidFuzz
    choices = {cid: name for cid, name in candidates.items()}

    results = process.extract(
        query.lower(),
        {k: v.lower() for k, v in choices.items()},
        scorer=fuzz.token_sort_ratio,
        limit=limit,
        score_cutoff=threshold,
    )

    matches: list[FuzzyMatch] = []
    for _matched_name, score, key in results:
        matches.append(FuzzyMatch(
            matched_name=candidates[key],
            canonical_id=key,
            score=score,
        ))

    return sorted(matches, key=lambda m: m.score, reverse=True)


def is_fuzzy_match(
    query: str,
    candidate: str,
    threshold: float = DEFAULT_FUZZY_THRESHOLD,
) -> bool:
    """Quick check if two names are a fuzzy match."""
    return fuzzy_match_single(query, candidate, threshold) >= threshold
