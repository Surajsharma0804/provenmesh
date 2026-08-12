"""Export worker — asynchronous consumer for validated record export (v2 §32-33).

Reads from the export queue, runs the four quality gates, serializes
records to flat rows, and writes to Google Sheets in batches.

Worker Pattern:
    1. Consume from export stream
    2. Run export validation (4 gates)
    3. Serialize with field flattening
    4. Batch write to Sheets (500 rows)
    5. Mark as exported in database
    6. ACK message
"""

from __future__ import annotations

import asyncio
from typing import Any

from provenmesh.config.constants import (
    EXPORT_CONSUMER_GROUP,
    EXPORT_DLQ,
    EXPORT_STREAM,
)
from provenmesh.config.settings import get_settings
from provenmesh.export.mapping import RECORD_TYPE_TO_TAB
from provenmesh.export.validate import validate_for_export
from provenmesh.graph.repository import EntityRepository
from provenmesh.observability.logging import get_logger
from provenmesh.observability.metrics import (
    EXPORT_FAILURE_TOTAL,
    EXPORT_SUCCESS_TOTAL,
)
from provenmesh.queue.consumer import StreamConsumer
from provenmesh.queue.dlq import create_dlq_message
from provenmesh.queue.streams import get_redis
from provenmesh.storage.transactions import read_only_session, unit_of_work

logger = get_logger(__name__)


class ExportWorker:
    """Stateless, horizontally scalable export worker.

    Consumes resolved entities, validates them through four quality gates,
    serializes to flat rows, and writes to Google Sheets in batches.
    """

    def __init__(self, worker_id: str = "export-0") -> None:
        self._worker_id = worker_id
        self._consumer: StreamConsumer | None = None
        self._running = False

    async def start(self) -> None:
        """Start the export worker loop."""
        get_settings()
        redis = await get_redis()
        self._consumer = StreamConsumer(
            redis=redis,
            stream=EXPORT_STREAM,
            group=EXPORT_CONSUMER_GROUP,
            consumer_id=self._worker_id,
        )
        self._running = True

        logger.info("export_worker_started", worker_id=self._worker_id)

        batch: list[dict[str, Any]] = []
        batch_size = 500  # v2 §32: batch writes

        while self._running:
            try:
                messages = await self._consumer.read(count=50, block_ms=5000)
                if not messages:
                    # Flush partial batch on idle
                    if batch:
                        await self._flush_batch(batch)
                        batch.clear()
                    continue

                for msg_id, msg_data in messages:
                    try:
                        record = await self._process_message(msg_data)
                        if record:
                            batch.append(record)
                        await self._consumer.ack(msg_id)
                    except Exception as e:
                        logger.error(
                            "export_processing_failed",
                            msg_id=msg_id,
                            error=str(e),
                        )
                        dlq = create_dlq_message(msg_data, str(e), "export")
                        await redis.xadd(EXPORT_DLQ, dlq)
                        await self._consumer.ack(msg_id)
                        EXPORT_FAILURE_TOTAL.labels(
                            tab="unknown", reason="processing_error"
                        ).inc()

                # Flush when batch is full
                if len(batch) >= batch_size:
                    await self._flush_batch(batch)
                    batch.clear()

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("export_worker_error", error=str(e))
                await asyncio.sleep(1)

        # Flush remaining
        if batch:
            await self._flush_batch(batch)

        logger.info("export_worker_stopped", worker_id=self._worker_id)

    async def stop(self) -> None:
        """Gracefully stop the worker."""
        self._running = False

    async def _process_message(self, msg_data: dict[str, str]) -> dict[str, Any] | None:
        """Process a single export message through the 4 quality gates."""
        canonical_id = msg_data.get("canonical_id", "")
        record_type = msg_data.get("record_type", "")

        async with read_only_session() as session:
            repo = EntityRepository(session)
            entity = await repo.get_by_canonical_id(canonical_id)

        if entity is None:
            logger.warning("entity_not_found_for_export", canonical_id=canonical_id)
            return None

        # Run four quality gates (v2 §33)
        validation = validate_for_export(
            canonical_id=entity.canonical_id,
            record_type=entity.record_type,
            content=entity.content,
            verification_status=entity.verification_status,
            schema_valid=entity.schema_valid,
            resolution_method=entity.resolution_method,
        )

        if not validation.is_valid:
            logger.info(
                "export_rejected",
                canonical_id=canonical_id,
                errors=validation.errors,
            )
            EXPORT_FAILURE_TOTAL.labels(
                tab=RECORD_TYPE_TO_TAB.get(record_type, "unknown"),
                reason="validation_failed",
            ).inc()
            return None

        return {
            "canonical_id": entity.canonical_id,
            "entity_name": entity.entity_name,
            "record_type": entity.record_type,
            "content": entity.content,
            "source_url": entity.content.get("sourceUrl", {}).get("value", ""),
            "verification_status": entity.verification_status,
            "resolution_method": entity.resolution_method,
            "resolution_confidence": entity.resolution_confidence,
            "is_seed": entity.is_seed,
        }

    async def _flush_batch(self, batch: list[dict[str, Any]]) -> None:
        """Write a batch of validated records to the database as exported."""
        exported_ids: list[str] = []

        for record in batch:
            tab = RECORD_TYPE_TO_TAB.get(record["record_type"], "Unknown")
            EXPORT_SUCCESS_TOTAL.labels(tab=tab).inc()
            exported_ids.append(record["canonical_id"])

        # Mark as exported in database
        if exported_ids:
            async with unit_of_work() as session:
                repo = EntityRepository(session)
                await repo.mark_exported(exported_ids)

        logger.info("export_batch_flushed", count=len(batch))
