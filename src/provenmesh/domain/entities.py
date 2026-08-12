"""Domain entities — Pydantic v2 models for all entity types.

Evidence-first design (v2 §21): every extracted field carries its value,
the source text span that supports it, and a confidence score.
This makes hallucination structurally harder, not just checked after the fact.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


# ─── Evidence-First Field ────────────────────────────────────────


class EvidencedField(BaseModel):
    """A single extracted value with its provenance chain (v2 §21).

    The grounding engine verifies `value` against `evidence` against the source
    chunk. If the evidence doesn't exist in the source text, the field is
    marked UNVERIFIED and excluded from export.
    """

    model_config = ConfigDict(frozen=True)

    value: str | float | int | None = None
    evidence: str | None = Field(
        default=None,
        description="Source text span that supports this value",
    )
    confidence: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Extraction confidence score",
    )


class EvidencedList(BaseModel):
    """A list of evidenced values (e.g., founders, skills)."""

    model_config = ConfigDict(frozen=True)

    items: list[EvidencedField] = Field(default_factory=list)


# ─── Source Provenance ───────────────────────────────────────────


class SourceInfo(BaseModel):
    """Provenance: where the raw data came from (v2 §29)."""

    model_config = ConfigDict(frozen=True)

    url: str
    source_name: str = ""
    fetched_at: datetime = Field(default_factory=datetime.utcnow)
    content_hash: str = ""
    fetch_tier: int = Field(default=1, ge=1, le=3)
    raw_s3_key: str = ""


# ─── Internal Metadata ──────────────────────────────────────────


class RecordMetadata(BaseModel):
    """Internal metadata attached to every record (PDF §8.1, v2 §28).

    These fields are used for quality control and are stripped before
    export unless the reviewer wants them.
    """

    content_hash: str = ""
    schema_version: str = "1.0"
    date_confidence: str = "strict"
    verification_status: str = "unverified"
    canonical_id: str = ""
    correlation_id: str = ""
    processing_state: str = "DISCOVERED"
    extracted_at: datetime | None = None
    resolved_at: datetime | None = None
    exported_at: datetime | None = None
    attempt_count: int = 0
    last_error: str | None = None


# ─── Key Person ──────────────────────────────────────────────────


class KeyPerson(BaseModel):
    """A person associated with an entity (founder, author, etc.)."""

    name: EvidencedField = Field(default_factory=EvidencedField)
    role: EvidencedField = Field(default_factory=EvidencedField)


# ─── Canonical Entity Types ─────────────────────────────────────


class BaseEntity(BaseModel):
    """Base for all entity types with shared provenance and metadata."""

    model_config = ConfigDict(populate_by_name=True)

    schema_version: str = "1.0"
    record_type: str
    source: SourceInfo
    metadata: RecordMetadata = Field(default_factory=RecordMetadata)


class StartupEntity(BaseEntity):
    """AI Startup entity — first of four canonical types (PDF §8.1)."""

    record_type: str = "STARTUP"

    entity_name: EvidencedField = Field(default_factory=EvidencedField)
    description: EvidencedField = Field(default_factory=EvidencedField)
    founded_date: EvidencedField = Field(default_factory=EvidencedField)
    founders: list[EvidencedField] = Field(default_factory=list)
    headquarters: EvidencedField = Field(default_factory=EvidencedField)
    industry: EvidencedField = Field(default_factory=EvidencedField)
    sub_industry: EvidencedField = Field(default_factory=EvidencedField)
    funding_total: EvidencedField = Field(default_factory=EvidencedField)
    last_funding_round: EvidencedField = Field(default_factory=EvidencedField)
    last_funding_date: EvidencedField = Field(default_factory=EvidencedField)
    investors: list[EvidencedField] = Field(default_factory=list)
    employee_count: EvidencedField = Field(default_factory=EvidencedField)
    website: EvidencedField = Field(default_factory=EvidencedField)
    linkedin_url: EvidencedField = Field(default_factory=EvidencedField)
    twitter_url: EvidencedField = Field(default_factory=EvidencedField)
    products: list[EvidencedField] = Field(default_factory=list)
    tech_stack: list[EvidencedField] = Field(default_factory=list)
    key_people: list[KeyPerson] = Field(default_factory=list)


class ProductEntity(BaseEntity):
    """AI Product entity — second canonical type (PDF §8.1)."""

    record_type: str = "PRODUCT"

    entity_name: EvidencedField = Field(default_factory=EvidencedField)
    description: EvidencedField = Field(default_factory=EvidencedField)
    company: EvidencedField = Field(default_factory=EvidencedField)
    category: EvidencedField = Field(default_factory=EvidencedField)
    sub_category: EvidencedField = Field(default_factory=EvidencedField)
    launch_date: EvidencedField = Field(default_factory=EvidencedField)
    pricing: EvidencedField = Field(default_factory=EvidencedField)
    pricing_model: EvidencedField = Field(default_factory=EvidencedField)
    features: list[EvidencedField] = Field(default_factory=list)
    platforms: list[EvidencedField] = Field(default_factory=list)
    tech_stack: list[EvidencedField] = Field(default_factory=list)
    website: EvidencedField = Field(default_factory=EvidencedField)
    github_url: EvidencedField = Field(default_factory=EvidencedField)
    rating: EvidencedField = Field(default_factory=EvidencedField)
    user_count: EvidencedField = Field(default_factory=EvidencedField)


class PaperEntity(BaseEntity):
    """Research Paper entity — third canonical type (PDF §8.1, §3.3)."""

    record_type: str = "PAPER"

    entity_name: EvidencedField = Field(default_factory=EvidencedField)
    title: EvidencedField = Field(default_factory=EvidencedField)
    abstract: EvidencedField = Field(default_factory=EvidencedField)
    authors: list[EvidencedField] = Field(default_factory=list)
    published_date: EvidencedField = Field(default_factory=EvidencedField)
    journal: EvidencedField = Field(default_factory=EvidencedField)
    conference: EvidencedField = Field(default_factory=EvidencedField)
    arxiv_id: EvidencedField = Field(default_factory=EvidencedField)
    doi: EvidencedField = Field(default_factory=EvidencedField)
    pdf_url: EvidencedField = Field(default_factory=EvidencedField)
    github_url: EvidencedField = Field(default_factory=EvidencedField)
    github_stars: EvidencedField = Field(default_factory=EvidencedField)
    citations: EvidencedField = Field(default_factory=EvidencedField)
    categories: list[EvidencedField] = Field(default_factory=list)
    keywords: list[EvidencedField] = Field(default_factory=list)
    affiliations: list[EvidencedField] = Field(default_factory=list)
    related_startups: list[EvidencedField] = Field(default_factory=list)


class JobEntity(BaseEntity):
    """AI Job listing entity — fourth canonical type (PDF §8.1)."""

    record_type: str = "JOB"

    entity_name: EvidencedField = Field(default_factory=EvidencedField)
    title: EvidencedField = Field(default_factory=EvidencedField)
    company: EvidencedField = Field(default_factory=EvidencedField)
    location: EvidencedField = Field(default_factory=EvidencedField)
    remote_policy: EvidencedField = Field(default_factory=EvidencedField)
    employment_type: EvidencedField = Field(default_factory=EvidencedField)
    seniority_level: EvidencedField = Field(default_factory=EvidencedField)
    salary_min: EvidencedField = Field(default_factory=EvidencedField)
    salary_max: EvidencedField = Field(default_factory=EvidencedField)
    salary_currency: EvidencedField = Field(default_factory=EvidencedField)
    description: EvidencedField = Field(default_factory=EvidencedField)
    requirements: list[EvidencedField] = Field(default_factory=list)
    skills: list[EvidencedField] = Field(default_factory=list)
    posted_date: EvidencedField = Field(default_factory=EvidencedField)
    expiry_date: EvidencedField = Field(default_factory=EvidencedField)
    application_url: EvidencedField = Field(default_factory=EvidencedField)
    department: EvidencedField = Field(default_factory=EvidencedField)


class NewsSignal(BaseEntity):
    """News signal — supporting intelligence, not a first-class entity (v2 §2)."""

    record_type: str = "NEWS_SIGNAL"

    title: EvidencedField = Field(default_factory=EvidencedField)
    summary: EvidencedField = Field(default_factory=EvidencedField)
    published_date: EvidencedField = Field(default_factory=EvidencedField)
    author: EvidencedField = Field(default_factory=EvidencedField)
    publisher: EvidencedField = Field(default_factory=EvidencedField)
    category: EvidencedField = Field(default_factory=EvidencedField)
    mentioned_entities: list[EvidencedField] = Field(default_factory=list)
    sentiment: EvidencedField = Field(default_factory=EvidencedField)
    key_topics: list[EvidencedField] = Field(default_factory=list)
    original_url: EvidencedField = Field(default_factory=EvidencedField)


# ─── Entity Type Registry ───────────────────────────────────────

ENTITY_TYPE_MAP: dict[str, type[BaseEntity]] = {
    "STARTUP": StartupEntity,
    "PRODUCT": ProductEntity,
    "PAPER": PaperEntity,
    "JOB": JobEntity,
    "NEWS_SIGNAL": NewsSignal,
}


def create_entity(record_type: str, **kwargs: Any) -> BaseEntity:
    """Factory function to create the correct entity type."""
    entity_cls = ENTITY_TYPE_MAP.get(record_type)
    if entity_cls is None:
        msg = f"Unknown record type: {record_type}"
        raise ValueError(msg)
    return entity_cls(**kwargs)
