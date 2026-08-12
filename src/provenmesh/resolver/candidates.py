"""Candidate retrieval — efficient pre-filtering before expensive matching (v2 §24).

Instead of comparing every entity against every seed (O(n×m)):
    1. Normalized prefix index → O(1) lookup
    2. Token inverted index → O(k) where k = matching tokens
    3. pgvector ANN → O(log n) approximate nearest neighbors

Then run RapidFuzz/embedding only against candidates.
"""

from __future__ import annotations

from collections import defaultdict

from provenmesh.observability.logging import get_logger
from provenmesh.resolver.normalization import normalize_entity_name

logger = get_logger(__name__)


class CandidateIndex:
    """In-memory candidate retrieval index for efficient pre-filtering.

    Builds two indexes:
        1. Prefix index: first 3 chars of normalized name → candidates
        2. Token index: each word → candidates

    This reduces fuzzy matching from O(n) to O(k) where k << n.
    """

    def __init__(self) -> None:
        self._prefix_index: dict[str, set[str]] = defaultdict(set)
        self._token_index: dict[str, set[str]] = defaultdict(set)
        self._all_ids: set[str] = set()

    def add(self, canonical_id: str, name: str) -> None:
        """Add an entity to the candidate index."""
        normalized = normalize_entity_name(name)
        self._all_ids.add(canonical_id)

        # Prefix index (first 3 chars)
        if len(normalized) >= 3:
            prefix = normalized[:3]
            self._prefix_index[prefix].add(canonical_id)

        # Token index (each word)
        for token in normalized.split():
            if len(token) >= 2:
                self._token_index[token].add(canonical_id)

    def get_candidates(self, query: str, max_candidates: int = 50) -> set[str]:
        """Retrieve candidate IDs for a query using index-based pre-filtering.

        Strategy:
            1. Check prefix index
            2. Check token index
            3. Union results, cap at max_candidates
        """
        normalized = normalize_entity_name(query)
        candidates: set[str] = set()

        # Prefix lookup
        if len(normalized) >= 3:
            prefix = normalized[:3]
            candidates.update(self._prefix_index.get(prefix, set()))

        # Token lookup
        for token in normalized.split():
            if len(token) >= 2:
                candidates.update(self._token_index.get(token, set()))

        # If we found nothing via index, fall back to all (for very short names)
        if not candidates and len(normalized) < 3:
            candidates = set(list(self._all_ids)[:max_candidates])

        # Cap results
        if len(candidates) > max_candidates:
            candidates = set(list(candidates)[:max_candidates])

        return candidates

    @property
    def total_indexed(self) -> int:
        return len(self._all_ids)

    def clear(self) -> None:
        self._prefix_index.clear()
        self._token_index.clear()
        self._all_ids.clear()
