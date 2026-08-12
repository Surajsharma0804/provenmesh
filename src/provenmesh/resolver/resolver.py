"""Entity resolver — deterministic → fuzzy → embedding cascade (PDF §6, v2 §23-25).

Resolution cascade:
    1. Exact seed match → confidence 1.0
    2. Normalized seed match → confidence 0.98
    3. RapidFuzz token_sort_ratio ≥ 85 → accept
    4. Sentence-Transformer embedding cosine ≥ 0.88 → accept
    5. 0.75 ≤ score < 0.88 → route to human review queue
    6. score < 0.75 → new entity

Entity IDs are deterministic slugs: {type}_{kebab-case-name}
"""

from __future__ import annotations

import re
import uuid
from typing import Any

import numpy as np
from rapidfuzz import fuzz
from sentence_transformers import SentenceTransformer

from provenmesh.config.settings import get_settings
from provenmesh.domain.enums import ResolutionMethod, ReviewStatus
from provenmesh.observability.logging import get_logger
from provenmesh.observability.metrics import (
    ENTITY_RESOLUTION_TOTAL,
    ENTITY_REVIEW_TOTAL,
)
from provenmesh.resolver.seeds import SeedEntity, SeedStore
from provenmesh.security.sanitization import sanitize_entity_name

logger = get_logger(__name__)


class ResolutionResult:
    """Result of entity resolution."""

    def __init__(
        self,
        canonical_id: str,
        canonical_name: str,
        method: ResolutionMethod,
        confidence: float,
        is_new: bool = False,
        needs_review: bool = False,
        matched_seed: SeedEntity | None = None,
    ) -> None:
        self.canonical_id = canonical_id
        self.canonical_name = canonical_name
        self.method = method
        self.confidence = confidence
        self.is_new = is_new
        self.needs_review = needs_review
        self.matched_seed = matched_seed


class EntityResolver:
    """Multi-strategy entity resolver with human review routing.

    This is the disambiguation engine that prevents duplicate entities
    in the graph. It operates in a strict cascade — cheaper strategies
    are tried first, expensive ML-based matching only when needed.
    """

    def __init__(self, seed_store: SeedStore | None = None) -> None:
        self._settings = get_settings()
        self._seed_store = seed_store or SeedStore()
        self._embedding_model: SentenceTransformer | None = None
        self._embedding_cache: dict[str, np.ndarray] = {}

        # Thresholds from config (PDF §6.2)
        self._fuzzy_threshold = self._settings.fuzzy_threshold  # 85
        self._embedding_accept = self._settings.embedding_accept_threshold  # 0.88
        self._review_low = self._settings.review_threshold  # 0.75

    def _get_embedding_model(self) -> SentenceTransformer:
        """Lazy-load the embedding model."""
        if self._embedding_model is None:
            self._embedding_model = SentenceTransformer("all-MiniLM-L6-v2")
        return self._embedding_model

    async def resolve(
        self,
        entity_name: str,
        record_type: str,
        entity_data: dict[str, Any] | None = None,
    ) -> ResolutionResult:
        """Resolve an extracted entity to a canonical ID.

        Cascade: exact → normalized → fuzzy → embedding → review/new
        """
        if not entity_name or not entity_name.strip():
            return ResolutionResult(
                canonical_id=self._generate_id(record_type, "unknown"),
                canonical_name="unknown",
                method=ResolutionMethod.UNRESOLVED,
                confidence=0.0,
                is_new=True,
            )

        clean_name = entity_name.strip()

        # Stage 1: Exact seed match (PDF §6.1)
        seed = self._seed_store.exact_match(clean_name)
        if seed:
            ENTITY_RESOLUTION_TOTAL.labels(method="exact").inc()
            return ResolutionResult(
                canonical_id=seed.canonical_id,
                canonical_name=seed.canonical_name,
                method=ResolutionMethod.EXACT,
                confidence=1.0,
                matched_seed=seed,
            )

        # Stage 2: Normalized match (PDF §6.1)
        seed = self._seed_store.normalized_match(clean_name)
        if seed:
            ENTITY_RESOLUTION_TOTAL.labels(method="normalized").inc()
            return ResolutionResult(
                canonical_id=seed.canonical_id,
                canonical_name=seed.canonical_name,
                method=ResolutionMethod.NORMALIZED,
                confidence=0.98,
                matched_seed=seed,
            )

        # Stage 3: Fuzzy matching (PDF §6.2)
        fuzzy_result = self._fuzzy_match(clean_name, record_type)
        if fuzzy_result:
            ENTITY_RESOLUTION_TOTAL.labels(method="fuzzy").inc()
            return fuzzy_result

        # Stage 4: Embedding similarity (PDF §6.2)
        embedding_result = self._embedding_match(clean_name, record_type)
        if embedding_result:
            if embedding_result.needs_review:
                ENTITY_REVIEW_TOTAL.inc()
            else:
                ENTITY_RESOLUTION_TOTAL.labels(method="embedding").inc()
            return embedding_result

        # Stage 5: New entity
        ENTITY_RESOLUTION_TOTAL.labels(method="new").inc()
        canonical_id = self._generate_id(record_type, clean_name)
        return ResolutionResult(
            canonical_id=canonical_id,
            canonical_name=clean_name,
            method=ResolutionMethod.UNRESOLVED,
            confidence=0.0,
            is_new=True,
        )

    def _fuzzy_match(
        self,
        name: str,
        record_type: str,
    ) -> ResolutionResult | None:
        """RapidFuzz token_sort_ratio matching against all seeds of same type."""
        seeds = self._seed_store.get_seeds_for_type(record_type)
        if not seeds:
            return None

        best_score = 0.0
        best_seed: SeedEntity | None = None
        normalized_name = sanitize_entity_name(name)

        for seed in seeds:
            # Check all names (canonical + aliases)
            names_to_check = [seed.normalized_name] + [
                sanitize_entity_name(a) for a in seed.aliases
            ]
            for check_name in names_to_check:
                score = fuzz.token_sort_ratio(normalized_name, check_name)
                if score > best_score:
                    best_score = score
                    best_seed = seed

        if best_seed and best_score >= self._fuzzy_threshold:
            return ResolutionResult(
                canonical_id=best_seed.canonical_id,
                canonical_name=best_seed.canonical_name,
                method=ResolutionMethod.FUZZY,
                confidence=best_score / 100.0,
                matched_seed=best_seed,
            )

        return None

    def _embedding_match(
        self,
        name: str,
        record_type: str,
    ) -> ResolutionResult | None:
        """Sentence-Transformer cosine similarity matching (PDF §6.2)."""
        seeds = self._seed_store.get_seeds_for_type(record_type)
        if not seeds:
            return None

        model = self._get_embedding_model()

        # Get embedding for input name
        name_embedding = self._get_or_compute_embedding(name, model)

        best_similarity = 0.0
        best_seed: SeedEntity | None = None

        for seed in seeds:
            seed_embedding = self._get_or_compute_embedding(seed.canonical_name, model)
            similarity = float(np.dot(name_embedding, seed_embedding) / (
                np.linalg.norm(name_embedding) * np.linalg.norm(seed_embedding)
            ))

            if similarity > best_similarity:
                best_similarity = similarity
                best_seed = seed

        if best_seed is None:
            return None

        # Accept: cosine ≥ 0.88
        if best_similarity >= self._embedding_accept:
            return ResolutionResult(
                canonical_id=best_seed.canonical_id,
                canonical_name=best_seed.canonical_name,
                method=ResolutionMethod.EMBEDDING,
                confidence=best_similarity,
                matched_seed=best_seed,
            )

        # Review band: 0.75 ≤ cosine < 0.88 (PDF §6.3)
        if best_similarity >= self._review_low:
            return ResolutionResult(
                canonical_id=best_seed.canonical_id,
                canonical_name=best_seed.canonical_name,
                method=ResolutionMethod.EMBEDDING,
                confidence=best_similarity,
                needs_review=True,
                matched_seed=best_seed,
            )

        # Below 0.75 → no match
        return None

    def _get_or_compute_embedding(
        self,
        text: str,
        model: SentenceTransformer,
    ) -> np.ndarray:
        """Get or compute embedding with cache."""
        if text not in self._embedding_cache:
            self._embedding_cache[text] = model.encode(text, convert_to_numpy=True)
        return self._embedding_cache[text]

    @staticmethod
    def _generate_id(record_type: str, name: str) -> str:
        """Generate a deterministic canonical ID.

        Format: {type_prefix}_{kebab-case-name}
        """
        prefix = record_type.lower()
        slug = re.sub(r"[^a-z0-9]+", "-", name.lower().strip()).strip("-")
        if not slug:
            slug = uuid.uuid4().hex[:8]
        return f"{prefix}_{slug}"

    @property
    def seed_store(self) -> SeedStore:
        return self._seed_store
