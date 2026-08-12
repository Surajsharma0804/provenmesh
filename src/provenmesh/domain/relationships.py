"""Domain relationship models (PDF §8.2, Appendix D, v2 §26–27).

The graph is the product. Flat entity tables answer "what exists."
Relationships answer "how does it connect" — which is the actual
product value proposition.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from provenmesh.domain.enums import RelationType


class RelationshipEdge(BaseModel):
    """An explicit edge in the intelligence graph.

    Idempotency (v2 §27): UNIQUE(source_id, target_id, relation_type, source_url)
    prevents duplicate relationships after retries.
    """

    model_config = ConfigDict(frozen=True)

    source_id: str = Field(
        ...,
        description="Canonical ID of the source entity (e.g., person_amara-okeke)",
    )
    target_id: str = Field(
        ...,
        description="Canonical ID of the target entity (e.g., startup_openai)",
    )
    relation_type: RelationType = Field(
        ...,
        description="Relationship type from the PDF's enumeration",
    )
    confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Confidence from extraction + resolution stage",
    )
    source_url: str = Field(
        ...,
        description="Original page the relationship was extracted from",
    )
    source_content_hash: str = Field(
        default="",
        description="Content hash of the source page for provenance",
    )
    evidence_text: str = Field(
        default="",
        description="Text span from which the relationship was extracted",
    )
    collected_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="ISO-8601 extraction timestamp",
    )

    @property
    def idempotency_key(self) -> str:
        """Unique key for deduplication (v2 §27)."""
        return f"{self.source_id}:{self.target_id}:{self.relation_type}:{self.source_url}"


class RelationshipCandidate(BaseModel):
    """A potential relationship discovered during extraction, before resolution."""

    raw_source_name: str
    raw_target_name: str
    relation_type: RelationType
    evidence_text: str
    confidence: float = 0.0
    source_url: str = ""
    content_hash: str = ""
