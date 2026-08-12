"""Evidence and provenance domain models (v2 §21, §29).

Every important value is traceable:
    Entity → Field → Evidence → Source → Raw S3 object

This is what turns ProvenMesh from a scraper into a provenance-aware
intelligence graph.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from provenmesh.domain.enums import FieldVerification


class EvidenceRecord(BaseModel):
    """A single piece of evidence linking an extracted value to source text.

    The grounding engine creates one of these for every field it verifies.
    Failed verifications still get an evidence record — with status UNVERIFIED —
    so the audit trail is complete.
    """

    model_config = ConfigDict(frozen=True)

    evidence_id: str = ""
    entity_id: str = ""
    field_name: str = ""
    extracted_value: str = ""
    evidence_text: str = Field(
        default="",
        description="The exact span from the source text that supports this value",
    )
    source_url: str = ""
    source_content_hash: str = ""
    raw_s3_key: str = ""
    verification_status: FieldVerification = FieldVerification.UNVERIFIED
    fuzzy_score: float = Field(
        default=0.0,
        description="Fuzzy match score between value and evidence span",
    )
    verified_at: datetime | None = None
    correlation_id: str = ""


class ProvenanceChain(BaseModel):
    """Full provenance chain for a single entity (v2 §29).

    Links: Entity → Fields → Evidence Records → Source → Raw S3 Object
    """

    entity_id: str
    record_type: str
    canonical_id: str = ""
    source_url: str = ""
    raw_s3_key: str = ""
    content_hash: str = ""
    evidence_records: list[EvidenceRecord] = Field(default_factory=list)
    grounded_field_count: int = 0
    total_field_count: int = 0
    created_at: datetime = Field(default_factory=datetime.utcnow)

    @property
    def grounding_ratio(self) -> float:
        """Fraction of fields that passed grounding verification."""
        if self.total_field_count == 0:
            return 0.0
        return self.grounded_field_count / self.total_field_count


class CrawlManifest(BaseModel):
    """Metadata stored alongside every raw payload in S3 (v2 §9)."""

    model_config = ConfigDict(frozen=True)

    url: str
    source_name: str
    fetched_at: datetime = Field(default_factory=datetime.utcnow)
    status_code: int = 200
    content_type: str = "text/html"
    content_hash: str = ""
    content_length: int = 0
    etag: str = ""
    last_modified: str = ""
    fetch_tier: int = 1
    encoding: str = "utf-8"
    original_encoding: str = ""
    correlation_id: str = ""
    headers: dict[str, str] = Field(default_factory=dict)
