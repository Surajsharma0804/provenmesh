"""Seed entity management — known entities for deterministic matching (PDF §6.1).

Seed entities are pre-loaded canonical references. Any extracted entity
that exactly matches a seed is immediately resolved without fuzzy logic.

Seeds are loaded from the database and cached in memory.
Auto-promotion (v2 §25): entities verified by ≥3 independent sources
are promoted to seeds automatically.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from provenmesh.observability.logging import get_logger
from provenmesh.security.sanitization import sanitize_entity_name

logger = get_logger(__name__)


@dataclass
class SeedEntity:
    """A known canonical entity for deterministic matching."""

    canonical_id: str
    canonical_name: str
    normalized_name: str
    record_type: str
    aliases: list[str] = field(default_factory=list)
    source_count: int = 0  # Number of independent sources confirming this entity


class SeedStore:
    """In-memory seed entity store with exact and normalized lookup.

    Two-level lookup (PDF §6.1):
        1. Exact match: O(1) hash lookup
        2. Normalized match: O(1) hash lookup after normalization

    Both levels are deterministic — no fuzzy logic, no ML.
    """

    def __init__(self) -> None:
        # Exact name → seed
        self._exact: dict[str, SeedEntity] = {}
        # Normalized name → seed
        self._normalized: dict[str, SeedEntity] = {}
        # Canonical ID → seed
        self._by_id: dict[str, SeedEntity] = {}
        # All seeds by record type
        self._by_type: dict[str, list[SeedEntity]] = {}

    def add_seed(self, seed: SeedEntity) -> None:
        """Register a seed entity for matching."""
        self._exact[seed.canonical_name.lower()] = seed
        self._normalized[seed.normalized_name] = seed
        self._by_id[seed.canonical_id] = seed

        for alias in seed.aliases:
            self._exact[alias.lower()] = seed
            self._normalized[sanitize_entity_name(alias)] = seed

        self._by_type.setdefault(seed.record_type, []).append(seed)

    def exact_match(self, name: str) -> SeedEntity | None:
        """Try exact match (case-insensitive)."""
        return self._exact.get(name.lower())

    def normalized_match(self, name: str) -> SeedEntity | None:
        """Try normalized match (strips legal suffixes, etc.)."""
        normalized = sanitize_entity_name(name)
        return self._normalized.get(normalized)

    def get_by_id(self, canonical_id: str) -> SeedEntity | None:
        """Look up seed by canonical ID."""
        return self._by_id.get(canonical_id)

    def get_seeds_for_type(self, record_type: str) -> list[SeedEntity]:
        """Get all seeds for a record type (for fuzzy/embedding matching)."""
        return self._by_type.get(record_type, [])

    def promote_to_seed(
        self,
        canonical_id: str,
        name: str,
        record_type: str,
        source_count: int = 3,
    ) -> SeedEntity:
        """Auto-promote a resolved entity to seed status (v2 §25).

        Called when an entity is confirmed by ≥3 independent sources.
        """
        normalized = sanitize_entity_name(name)
        seed = SeedEntity(
            canonical_id=canonical_id,
            canonical_name=name,
            normalized_name=normalized,
            record_type=record_type,
            source_count=source_count,
        )
        self.add_seed(seed)
        logger.info(
            "entity_promoted_to_seed",
            canonical_id=canonical_id,
            name=name,
            sources=source_count,
        )
        return seed

    @property
    def total_seeds(self) -> int:
        return len(self._by_id)

    def load_from_json(self, json_data: list[dict]) -> int:
        """Bulk load seeds from JSON (for initial seeding)."""
        count = 0
        for entry in json_data:
            seed = SeedEntity(
                canonical_id=entry["canonical_id"],
                canonical_name=entry["name"],
                normalized_name=sanitize_entity_name(entry["name"]),
                record_type=entry.get("record_type", "STARTUP"),
                aliases=entry.get("aliases", []),
            )
            self.add_seed(seed)
            count += 1
        return count
