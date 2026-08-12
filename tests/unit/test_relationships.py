"""Tests for domain/relationships.py — RelationshipEdge and RelationshipCandidate."""
from __future__ import annotations

import pytest

from provenmesh.domain.enums import RelationType
from provenmesh.domain.relationships import RelationshipCandidate, RelationshipEdge

# Rebuild models to resolve forward references from `from __future__ import annotations`
RelationshipEdge.model_rebuild()
RelationshipCandidate.model_rebuild()


class TestRelationshipEdge:
    def test_creation(self) -> None:
        edge = RelationshipEdge(
            source_id="person_sam-altman",
            target_id="startup_openai",
            relation_type=RelationType.FOUNDED_BY,
            confidence=0.95,
            source_url="https://example.com/article",
            evidence_text="Sam Altman co-founded OpenAI",
        )
        assert edge.source_id == "person_sam-altman"
        assert edge.target_id == "startup_openai"
        assert edge.confidence == 0.95

    def test_idempotency_key(self) -> None:
        edge = RelationshipEdge(
            source_id="a",
            target_id="b",
            relation_type=RelationType.BUILDS_PRODUCT,
            confidence=0.9,
            source_url="https://src.com",
        )
        key = edge.idempotency_key
        assert "a:" in key
        assert "b:" in key
        assert "BUILDS_PRODUCT" in key
        assert "https://src.com" in key

    def test_frozen(self) -> None:
        edge = RelationshipEdge(
            source_id="a", target_id="b",
            relation_type=RelationType.WORKS_AT,
            confidence=0.8, source_url="https://x.com",
        )
        with pytest.raises(Exception, match=r"frozen"):
            edge.source_id = "c"  # type: ignore


class TestRelationshipCandidate:
    def test_creation(self) -> None:
        candidate = RelationshipCandidate(
            raw_source_name="Sam Altman",
            raw_target_name="OpenAI",
            relation_type=RelationType.FOUNDED_BY,
            evidence_text="Sam Altman co-founded OpenAI",
            confidence=0.92,
            source_url="https://example.com",
            content_hash="abc123",
        )
        assert candidate.raw_source_name == "Sam Altman"
        assert candidate.confidence == 0.92

    def test_defaults(self) -> None:
        candidate = RelationshipCandidate(
            raw_source_name="A",
            raw_target_name="B",
            relation_type=RelationType.CITES,
            evidence_text="text",
        )
        assert candidate.confidence == 0.0
        assert candidate.source_url == ""
        assert candidate.content_hash == ""
