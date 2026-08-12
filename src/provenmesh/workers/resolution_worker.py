"""Resolution worker — entity resolution + relationship persistence.

Pipeline: deserialize entity → resolve → persist entity → persist relationships → ACK
"""

from __future__ import annotations

import asyncio
import json
import uuid
from datetime import datetime, timezone

from provenmesh.config.constants import (
    RESOLUTION_CONSUMER_GROUP,
    RESOLUTION_DLQ,
    RESOLUTION_STREAM,
)
from provenmesh.graph.models import EntityRecord, EvidenceRow, RelationshipRecord
from provenmesh.graph.repository import (
    CrawlItemRepository,
    EntityRepository,
    EvidenceRepository,
    RelationshipRepository,
)
from provenmesh.observability.health import HealthStatus
from provenmesh.observability.logging import get_logger, set_correlation_id
from provenmesh.queue.consumer import QueueConsumer
from provenmesh.queue.messages import QueueMessage, ResolutionMessage
from provenmesh.resolver.resolver import EntityResolver
from provenmesh.resolver.review_queue import ReviewItem, ReviewQueue
from provenmesh.resolver.seeds import SeedStore
from provenmesh.security.sanitization import sanitize_entity_name
from provenmesh.storage.transactions import unit_of_work

logger = get_logger(__name__)


class ResolutionWorker:
    """Resolves entities, persists to graph, and creates relationships.

    This is the final processing stage before export. After resolution:
        - Entity has a canonical_id
        - Relationships are materialized in the DB
        - Evidence records are persisted
        - Review-band matches are queued for human review
    """

    def __init__(self, worker_id: str = "resolver-0") -> None:
        self._worker_id = worker_id
        self._seed_store = SeedStore()
        self._resolver = EntityResolver(self._seed_store)
        self._review_queue = ReviewQueue()
        self._health = HealthStatus()

    async def handle_message(self, message: QueueMessage) -> None:
        msg = ResolutionMessage.model_validate(message.model_dump())
        set_correlation_id(msg.correlation_id)

        # Deserialize entity data
        entity_data = json.loads(msg.entity_data) if msg.entity_data else {}
        relationship_candidates = json.loads(msg.relationship_candidates) if msg.relationship_candidates else []

        fields = entity_data.get("fields", {})
        entity_name_field = fields.get("entityName", fields.get("title", {}))
        entity_name = ""
        if isinstance(entity_name_field, dict):
            entity_name = str(entity_name_field.get("value", ""))
        elif isinstance(entity_name_field, str):
            entity_name = entity_name_field

        if not entity_name:
            logger.warning("resolution_skipped_no_name", correlation_id=msg.correlation_id)
            return

        logger.info(
            "resolution_started",
            entity_name=entity_name,
            record_type=msg.record_type,
        )

        # Resolve entity
        resolution = await self._resolver.resolve(
            entity_name=entity_name,
            record_type=msg.record_type,
            entity_data=fields,
        )

        # Handle review-band matches
        if resolution.needs_review:
            review_item = ReviewItem(
                review_id=str(uuid.uuid4()),
                extracted_name=entity_name,
                candidate_canonical_id=resolution.canonical_id,
                candidate_name=resolution.canonical_name,
                record_type=msg.record_type,
                similarity_score=resolution.confidence,
                resolution_method=resolution.method.value,
                source_url=entity_data.get("source_url", ""),
            )
            self._review_queue.add(review_item)

        # Persist to database
        async with unit_of_work() as session:
            entity_repo = EntityRepository(session)
            rel_repo = RelationshipRepository(session)
            evidence_repo = EvidenceRepository(session)
            crawl_repo = CrawlItemRepository(session)

            # Create/update entity
            entity_record = EntityRecord(
                canonical_id=resolution.canonical_id,
                record_type=msg.record_type,
                entity_name=entity_name,
                normalized_name=sanitize_entity_name(entity_name),
                content=fields,
                resolution_method=resolution.method.value,
                resolution_confidence=resolution.confidence,
                verification_status=entity_data.get("verification_status", "unverified"),
                grounding_ratio=entity_data.get("grounding_ratio", 0.0),
                schema_valid=entity_data.get("schema_valid", False),
                source_url=entity_data.get("source_url", ""),
                content_hash=entity_data.get("content_hash", ""),
                raw_s3_key=entity_data.get("raw_s3_key", ""),
            )
            await entity_repo.upsert(entity_record)

            # Persist relationships
            for rel_candidate in relationship_candidates:
                source_name = rel_candidate.get("source", "")
                target_name = rel_candidate.get("target", "")
                rel_type = rel_candidate.get("type", "")

                if not source_name or not target_name or not rel_type:
                    continue

                # Resolve source and target entities
                source_resolution = await self._resolver.resolve(source_name, msg.record_type)
                target_resolution = await self._resolver.resolve(target_name, msg.record_type)

                rel_record = RelationshipRecord(
                    source_id=source_resolution.canonical_id,
                    target_id=target_resolution.canonical_id,
                    relation_type=rel_type,
                    confidence=float(rel_candidate.get("confidence", 0.0)),
                    source_url=entity_data.get("source_url", ""),
                    source_content_hash=entity_data.get("content_hash", ""),
                    evidence_text=rel_candidate.get("evidence", ""),
                )
                await rel_repo.upsert(rel_record)

            # Update crawl item state
            source_url = entity_data.get("source_url", "")
            source_name = entity_data.get("source_name", "")
            if source_url and source_name:
                await crawl_repo.update_state(
                    source_url,
                    source_name,
                    "RESOLVED",
                    canonical_id=resolution.canonical_id,
                    resolved_at=datetime.now(timezone.utc),
                )

        # Auto-promote to seed if enough independent sources (v2 §25)
        if not resolution.is_new and resolution.confidence >= 0.95:
            async with unit_of_work() as session:
                entity_repo = EntityRepository(session)
                entity = await entity_repo.get_by_canonical_id(resolution.canonical_id)
                if entity and entity.source_count >= 3 and not entity.is_seed:
                    self._seed_store.promote_to_seed(
                        resolution.canonical_id,
                        entity_name,
                        msg.record_type,
                        entity.source_count,
                    )

        self._health.record_processed()
        logger.info(
            "resolution_completed",
            entity_name=entity_name,
            canonical_id=resolution.canonical_id,
            method=resolution.method.value,
            confidence=round(resolution.confidence, 3),
            is_new=resolution.is_new,
            needs_review=resolution.needs_review,
        )

    async def run(self, shutdown_event: asyncio.Event) -> None:
        consumer = QueueConsumer(
            stream=RESOLUTION_STREAM,
            group=RESOLUTION_CONSUMER_GROUP,
            consumer_name=self._worker_id,
            message_cls=ResolutionMessage,
            handler=self.handle_message,
            dlq_stream=RESOLUTION_DLQ,
        )
        self._health.set_ready()
        await consumer.run_loop(shutdown_event)
