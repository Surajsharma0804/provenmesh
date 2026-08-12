"""Domain enumerations — single source of truth for all categorical values.

Every enum here maps to a JSON schema enum or a database column constraint.
Adding a value here automatically propagates to validation, storage, and export.
"""

from __future__ import annotations

from enum import StrEnum, unique


@unique
class RecordType(StrEnum):
    """The four canonical entity types + news signal (PDF §8.1, §2 clarification)."""

    STARTUP = "STARTUP"
    PRODUCT = "PRODUCT"
    PAPER = "PAPER"
    JOB = "JOB"
    NEWS_SIGNAL = "NEWS_SIGNAL"


@unique
class RelationType(StrEnum):
    """Relationship types between entities (PDF §8.2)."""

    FOUNDED_BY = "FOUNDED_BY"
    BUILDS_PRODUCT = "BUILDS_PRODUCT"
    PUBLISHED_PAPER = "PUBLISHED_PAPER"
    CITES = "CITES"
    WORKS_AT = "WORKS_AT"


@unique
class VerificationStatus(StrEnum):
    """Field-level and record-level verification states (v2 §22).

    GROUNDED: every field verified against source text.
    PARTIAL: some fields grounded, others missing but non-critical.
    UNVERIFIED: one or more critical fields failed grounding.
    REJECTED: record failed multiple quality checks — never export.
    """

    GROUNDED = "grounded"
    PARTIAL = "partial"
    UNVERIFIED = "unverified"
    REJECTED = "rejected"


@unique
class FieldVerification(StrEnum):
    """Per-field verification states (v2 §22)."""

    GROUNDED = "GROUNDED"
    UNVERIFIED = "UNVERIFIED"
    MISSING = "MISSING"
    CONFLICTING = "CONFLICTING"


@unique
class DateConfidence(StrEnum):
    """Date parsing confidence levels (PDF §4.1)."""

    STRICT = "strict"
    HEURISTIC = "heuristic"


@unique
class FetchTier(StrEnum):
    """Tiered fetch strategy (PDF §7.1).

    TIER_1: plain aiohttp GET with rotating headers.
    TIER_2: Playwright async headless Chromium.
    TIER_3: Playwright + rotating residential/datacenter proxy pool.
    """

    TIER_1 = "tier_1"
    TIER_2 = "tier_2"
    TIER_3 = "tier_3"


@unique
class ProcessingState(StrEnum):
    """Processing state machine (v2 §10).

    Every item progresses through these states deterministically.
    Failure states allow targeted retry or DLQ routing.
    """

    # Happy path
    DISCOVERED = "DISCOVERED"
    QUEUED = "QUEUED"
    FETCHING = "FETCHING"
    FETCHED = "FETCHED"
    DEDUPLICATED = "DEDUPLICATED"
    EXTRACTION_PENDING = "EXTRACTION_PENDING"
    EXTRACTING = "EXTRACTING"
    EXTRACTED = "EXTRACTED"
    GROUNDING = "GROUNDING"
    GROUNDED = "GROUNDED"
    RESOLUTION_PENDING = "RESOLUTION_PENDING"
    RESOLVED = "RESOLVED"
    PERSISTED = "PERSISTED"
    EXPORT_PENDING = "EXPORT_PENDING"
    EXPORTED = "EXPORTED"

    # Failure states
    FETCH_FAILED = "FETCH_FAILED"
    EXTRACTION_FAILED = "EXTRACTION_FAILED"
    GROUNDING_FAILED = "GROUNDING_FAILED"
    RESOLUTION_FAILED = "RESOLUTION_FAILED"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    DEAD_LETTER = "DEAD_LETTER"


@unique
class CircuitState(StrEnum):
    """Circuit breaker states (PDF §5.1, v2 §15)."""

    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"


@unique
class ResolutionMethod(StrEnum):
    """Entity resolution method that produced the match (v2 §23)."""

    EXACT = "exact"
    NORMALIZED = "normalized"
    FUZZY = "fuzzy"
    EMBEDDING = "embedding"
    MANUAL = "manual"
    UNRESOLVED = "unresolved"


@unique
class ReviewStatus(StrEnum):
    """Human review queue status (PDF §6.3)."""

    PENDING = "pending"
    NEEDS_REVIEW = "needs_review"
    RESOLVED = "resolved"
    REJECTED = "rejected"


@unique
class ExportTab(StrEnum):
    """Google Sheets export tabs (PDF §12: 6-tab export)."""

    STARTUPS = "Startups"
    PRODUCTS = "Products"
    PAPERS = "Papers"
    JOBS = "Jobs"
    NEWS = "News"
    ENTITY_MAPPING_LOG = "Entity Mapping Log"
