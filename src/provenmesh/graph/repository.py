"""Repository layer — CRUD operations with idempotency (v2 §27-28).

All writes use ON CONFLICT DO UPDATE (upsert) to ensure idempotent
operations. Workers can safely retry without creating duplicates.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Sequence

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from provenmesh.graph.models import (
    CrawlItemRecord,
    EntityRecord,
    EvidenceRow,
    RelationshipRecord,
    ReviewItemRecord,
)
from provenmesh.observability.logging import get_logger

logger = get_logger(__name__)


class EntityRepository:
    """CRUD for entities with upsert semantics."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def upsert(self, entity: EntityRecord) -> EntityRecord:
        """Insert or update an entity by canonical_id.

        Uses PostgreSQL ON CONFLICT DO UPDATE for idempotency.
        """
        stmt = pg_insert(EntityRecord).values(
            canonical_id=entity.canonical_id,
            record_type=entity.record_type,
            entity_name=entity.entity_name,
            normalized_name=entity.normalized_name,
            content=entity.content,
            resolution_method=entity.resolution_method,
            resolution_confidence=entity.resolution_confidence,
            source_count=entity.source_count,
            is_seed=entity.is_seed,
            verification_status=entity.verification_status,
            grounding_ratio=entity.grounding_ratio,
            schema_valid=entity.schema_valid,
            embedding=entity.embedding,
            source_url=entity.source_url,
            content_hash=entity.content_hash,
            raw_s3_key=entity.raw_s3_key,
        ).on_conflict_do_update(
            index_elements=["canonical_id"],
            set_={
                "content": entity.content,
                "verification_status": entity.verification_status,
                "grounding_ratio": entity.grounding_ratio,
                "source_count": EntityRecord.source_count + 1,
                "updated_at": datetime.now(timezone.utc),
            },
        )
        await self._session.execute(stmt)
        await self._session.flush()

        # Retrieve the upserted record
        result = await self._session.execute(
            select(EntityRecord).where(EntityRecord.canonical_id == entity.canonical_id)
        )
        return result.scalar_one()

    async def get_by_canonical_id(self, canonical_id: str) -> EntityRecord | None:
        result = await self._session.execute(
            select(EntityRecord).where(EntityRecord.canonical_id == canonical_id)
        )
        return result.scalar_one_or_none()

    async def get_exportable(
        self,
        record_type: str,
        batch_size: int = 500,
        offset: int = 0,
    ) -> Sequence[EntityRecord]:
        """Get entities ready for export (grounded + schema-valid + resolved)."""
        result = await self._session.execute(
            select(EntityRecord)
            .where(
                EntityRecord.record_type == record_type,
                EntityRecord.verification_status.in_(["grounded", "partial"]),
                EntityRecord.schema_valid == True,  # noqa: E712
                EntityRecord.exported_at == None,  # noqa: E711
            )
            .order_by(EntityRecord.created_at)
            .limit(batch_size)
            .offset(offset)
        )
        return result.scalars().all()

    async def mark_exported(self, canonical_ids: list[str]) -> None:
        """Mark entities as exported."""
        await self._session.execute(
            update(EntityRecord)
            .where(EntityRecord.canonical_id.in_(canonical_ids))
            .values(exported_at=datetime.now(timezone.utc))
        )


class RelationshipRepository:
    """CRUD for relationship edges with dedup."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def upsert(self, rel: RelationshipRecord) -> None:
        """Insert or update a relationship edge."""
        stmt = pg_insert(RelationshipRecord).values(
            source_id=rel.source_id,
            target_id=rel.target_id,
            relation_type=rel.relation_type,
            confidence=rel.confidence,
            source_url=rel.source_url,
            source_content_hash=rel.source_content_hash,
            evidence_text=rel.evidence_text,
        ).on_conflict_do_update(
            constraint="uq_relationship_edge",
            set_={
                "confidence": rel.confidence,
                "evidence_text": rel.evidence_text,
            },
        )
        await self._session.execute(stmt)

    async def get_for_entity(self, canonical_id: str) -> Sequence[RelationshipRecord]:
        """Get all relationships for an entity (as source or target)."""
        result = await self._session.execute(
            select(RelationshipRecord).where(
                (RelationshipRecord.source_id == canonical_id)
                | (RelationshipRecord.target_id == canonical_id)
            )
        )
        return result.scalars().all()


class EvidenceRepository:
    """CRUD for evidence records."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def bulk_insert(self, records: list[EvidenceRow]) -> None:
        """Insert evidence records in batch."""
        self._session.add_all(records)
        await self._session.flush()

    async def get_for_entity(self, entity_id: str) -> Sequence[EvidenceRow]:
        result = await self._session.execute(
            select(EvidenceRow).where(EvidenceRow.entity_id == entity_id)
        )
        return result.scalars().all()


class CrawlItemRepository:
    """CRUD for crawl items with state machine tracking."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def upsert(self, item: CrawlItemRecord) -> None:
        stmt = pg_insert(CrawlItemRecord).values(
            url=item.url,
            source_name=item.source_name,
            record_type=item.record_type,
            processing_state=item.processing_state,
            correlation_id=item.correlation_id,
        ).on_conflict_do_update(
            constraint="uq_crawl_item_url_source",
            set_={"processing_state": item.processing_state},
        )
        await self._session.execute(stmt)

    async def update_state(
        self,
        url: str,
        source_name: str,
        new_state: str,
        **kwargs: Any,
    ) -> None:
        values: dict[str, Any] = {"processing_state": new_state}
        values.update(kwargs)
        await self._session.execute(
            update(CrawlItemRecord)
            .where(
                CrawlItemRecord.url == url,
                CrawlItemRecord.source_name == source_name,
            )
            .values(**values)
        )
