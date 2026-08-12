"""Embedding-based entity matching — semantic similarity (v2 §23-24).

Uses sentence-transformers for dense vector similarity.
Thresholds:
    ≥ 0.88 → auto-accept match
    0.75-0.88 → route to human review  # noqa: RUF002
    < 0.75 → treat as new entity
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

import numpy as np

from provenmesh.observability.logging import get_logger

logger = get_logger(__name__)

ACCEPT_THRESHOLD = 0.88
REVIEW_THRESHOLD = 0.75
MODEL_NAME = "all-MiniLM-L6-v2"


@dataclass(frozen=True)
class EmbeddingMatch:
    """Result of an embedding similarity match."""

    matched_name: str
    canonical_id: str
    similarity: float
    needs_review: bool = False


@lru_cache(maxsize=1)
def _get_model():
    """Lazy-load the sentence transformer model."""
    try:
        from sentence_transformers import SentenceTransformer
        logger.info("loading_embedding_model", model=MODEL_NAME)
        return SentenceTransformer(MODEL_NAME)
    except Exception as e:
        logger.warning("embedding_model_unavailable", error=str(e))
        return None


def compute_embedding(text: str) -> np.ndarray | None:
    """Compute a dense embedding for a text string."""
    model = _get_model()
    if model is None:
        return None
    try:
        return model.encode(text, normalize_embeddings=True)
    except Exception as e:
        logger.warning("embedding_computation_failed", text=text[:50], error=str(e))
        return None


def compute_similarity(embedding_a: np.ndarray, embedding_b: np.ndarray) -> float:
    """Compute cosine similarity between two normalized embeddings."""
    return float(np.dot(embedding_a, embedding_b))


def embedding_match(
    query: str,
    candidates: dict[str, tuple[str, np.ndarray]],
    accept_threshold: float = ACCEPT_THRESHOLD,
    review_threshold: float = REVIEW_THRESHOLD,
) -> EmbeddingMatch | None:
    """Match a query against pre-computed candidate embeddings.

    Args:
        query: Entity name to match
        candidates: Dict of {canonical_id: (name, embedding)}

    Returns:
        Best match if above review threshold, None otherwise
    """
    query_embedding = compute_embedding(query)
    if query_embedding is None:
        return None

    best_match: EmbeddingMatch | None = None
    best_similarity = 0.0

    for canonical_id, (name, embedding) in candidates.items():
        similarity = compute_similarity(query_embedding, embedding)
        if similarity > best_similarity:
            best_similarity = similarity
            needs_review = review_threshold <= similarity < accept_threshold
            best_match = EmbeddingMatch(
                matched_name=name,
                canonical_id=canonical_id,
                similarity=similarity,
                needs_review=needs_review,
            )

    if best_match and best_match.similarity >= review_threshold:
        return best_match
    return None


def batch_compute_embeddings(texts: list[str]) -> list[np.ndarray | None]:
    """Compute embeddings for a batch of texts efficiently."""
    model = _get_model()
    if model is None:
        return [None] * len(texts)
    try:
        embeddings = model.encode(texts, normalize_embeddings=True, batch_size=32)
        return list(embeddings)
    except Exception as e:
        logger.warning("batch_embedding_failed", count=len(texts), error=str(e))
        return [None] * len(texts)
