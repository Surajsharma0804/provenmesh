"""SQLAlchemy ORM models — the physical database schema (PDF §9, v2 §26-29).

Tables:
    entities: All canonical entities with JSONB content
    relationships: Graph edges between entities
    evidence_records: Per-field grounding evidence
    crawl_items: Crawl tracking and state machine
    review_items: Human review queue

Uniqueness constraints enforce idempotency (v2 §27):
    - entities: UNIQUE(canonical_id)
    - relationships: UNIQUE(source_id, target_id, relation_type, source_url)
    - crawl_items: UNIQUE(url, source_name)
"""

from __future__ import annotations

from datetime import datetime  # noqa: TC003 — required at runtime for SQLAlchemy

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""

    pass


class EntityRecord(Base):
    """Canonical entity table — stores all entity types with JSONB content.

    The content column holds the full evidence-first entity data.
    This enables schema-less evolution while keeping relational
    indexing for lookups and joins.
    """

    __tablename__ = "entities"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    canonical_id: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    record_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    entity_name: Mapped[str] = mapped_column(String(500), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(500), nullable=False, index=True)

    # Full entity content as JSONB (evidence-first structure)
    content: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    # Resolution metadata
    resolution_method: Mapped[str] = mapped_column(String(50), default="unresolved")
    resolution_confidence: Mapped[float] = mapped_column(Float, default=0.0)
    source_count: Mapped[int] = mapped_column(Integer, default=1)
    is_seed: Mapped[bool] = mapped_column(Boolean, default=False)

    # Quality
    verification_status: Mapped[str] = mapped_column(String(50), default="unverified", index=True)
    grounding_ratio: Mapped[float] = mapped_column(Float, default=0.0)
    schema_valid: Mapped[bool] = mapped_column(Boolean, default=False)

    # Embedding for similarity search (pgvector)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(384), nullable=True)

    # Provenance
    source_url: Mapped[str] = mapped_column(Text, default="")
    content_hash: Mapped[str] = mapped_column(String(64), default="")
    raw_s3_key: Mapped[str] = mapped_column(Text, default="")

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(),
    )
    exported_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("idx_entities_type_verification", "record_type", "verification_status"),
        Index("idx_entities_name_type", "normalized_name", "record_type"),
    )


class RelationshipRecord(Base):
    """Graph edge table — explicit relationships between entities (PDF §8.2)."""

    __tablename__ = "relationships"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    target_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    relation_type: Mapped[str] = mapped_column(String(50), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)

    # Provenance
    source_url: Mapped[str] = mapped_column(Text, default="")
    source_content_hash: Mapped[str] = mapped_column(String(64), default="")
    evidence_text: Mapped[str] = mapped_column(Text, default="")

    collected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(),
    )

    __table_args__ = (
        UniqueConstraint(
            "source_id", "target_id", "relation_type", "source_url",
            name="uq_relationship_edge",
        ),
        Index("idx_rel_source", "source_id"),
        Index("idx_rel_target", "target_id"),
        Index("idx_rel_type", "relation_type"),
    )


class EvidenceRow(Base):
    """Per-field grounding evidence — the audit trail (v2 §29)."""

    __tablename__ = "evidence_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    entity_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    field_name: Mapped[str] = mapped_column(String(255), nullable=False)
    extracted_value: Mapped[str] = mapped_column(Text, default="")
    evidence_text: Mapped[str] = mapped_column(Text, default="")
    source_url: Mapped[str] = mapped_column(Text, default="")
    source_content_hash: Mapped[str] = mapped_column(String(64), default="")
    raw_s3_key: Mapped[str] = mapped_column(Text, default="")
    verification_status: Mapped[str] = mapped_column(String(50), default="UNVERIFIED")
    fuzzy_score: Mapped[float] = mapped_column(Float, default=0.0)
    correlation_id: Mapped[str] = mapped_column(String(36), default="")
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("idx_evidence_entity_field", "entity_id", "field_name"),
    )


class CrawlItemRecord(Base):
    """Crawl item tracking — state machine for every discovered URL (v2 §10)."""

    __tablename__ = "crawl_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    source_name: Mapped[str] = mapped_column(String(100), nullable=False)
    record_type: Mapped[str] = mapped_column(String(50), nullable=False)

    # State machine
    processing_state: Mapped[str] = mapped_column(String(50), default="DISCOVERED", index=True)

    # Content tracking
    content_hash: Mapped[str] = mapped_column(String(64), default="")
    raw_s3_key: Mapped[str] = mapped_column(Text, default="")
    fetch_tier: Mapped[int] = mapped_column(Integer, default=1)
    status_code: Mapped[int] = mapped_column(Integer, default=0)

    # Error tracking
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str] = mapped_column(Text, default="")

    # Correlation
    correlation_id: Mapped[str] = mapped_column(String(36), default="", index=True)
    canonical_id: Mapped[str] = mapped_column(String(255), default="")

    # Timestamps
    discovered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(),
    )
    fetched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    extracted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    exported_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        UniqueConstraint("url", "source_name", name="uq_crawl_item_url_source"),
        Index("idx_crawl_state", "processing_state"),
        Index("idx_crawl_source_type", "source_name", "record_type"),
    )


class ReviewItemRecord(Base):
    """Human review queue — persistent storage for uncertain matches."""

    __tablename__ = "review_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    extracted_name: Mapped[str] = mapped_column(String(500), nullable=False)
    candidate_canonical_id: Mapped[str] = mapped_column(String(255), default="")
    candidate_name: Mapped[str] = mapped_column(String(500), default="")
    record_type: Mapped[str] = mapped_column(String(50), nullable=False)
    similarity_score: Mapped[float] = mapped_column(Float, default=0.0)
    resolution_method: Mapped[str] = mapped_column(String(50), default="")
    evidence_summary: Mapped[str] = mapped_column(Text, default="")
    source_url: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(50), default="needs_review", index=True)
    reviewer: Mapped[str] = mapped_column(String(100), default="")
    decision: Mapped[str] = mapped_column(String(50), default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(),
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ExportRunRecord(Base):
    """Export run tracking — audit log for Google Sheets exports."""

    __tablename__ = "export_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(String(36), unique=True, nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(),
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(50), default="running")
    records_exported: Mapped[int] = mapped_column(Integer, default=0)
    records_skipped: Mapped[int] = mapped_column(Integer, default=0)
    records_failed: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[str] = mapped_column(Text, default="")
