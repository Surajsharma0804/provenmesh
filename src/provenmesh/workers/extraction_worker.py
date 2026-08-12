"""Extraction worker — LLM extraction + grounding + emit resolution messages.

Pipeline: retrieve S3 → chunk → LLM extract → ground → validate schema → emit
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from provenmesh.config.constants import (
    EXTRACTION_CONSUMER_GROUP,
    EXTRACTION_DLQ,
    EXTRACTION_STREAM,
    RESOLUTION_STREAM,
)
from provenmesh.extraction.orchestrator import ExtractionOrchestrator
from provenmesh.graph.repository import CrawlItemRepository
from provenmesh.grounding.engine import GroundingEngine
from provenmesh.grounding.schema_validator import validate_record
from provenmesh.observability.health import HealthStatus
from provenmesh.observability.logging import get_logger, set_correlation_id
from provenmesh.queue.consumer import QueueConsumer
from provenmesh.queue.messages import ExtractionMessage, QueueMessage, ResolutionMessage
from provenmesh.queue.producer import QueueProducer
from provenmesh.raw_store.s3 import retrieve_raw_payload
from provenmesh.storage.transactions import unit_of_work

if TYPE_CHECKING:
    import asyncio

logger = get_logger(__name__)


class ExtractionWorker:
    """Extracts structured data from raw pages using LLM orchestrator.

    Sequence:
        1. Retrieve raw HTML from S3
        2. LLM extraction (evidence-first)
        3. Ground every field against source text
        4. Validate against JSON schema
        5. Persist extraction result
        6. Emit resolution message
    """

    def __init__(self, worker_id: str = "extraction-0") -> None:
        self._worker_id = worker_id
        self._orchestrator = ExtractionOrchestrator()
        self._grounding_engine = GroundingEngine()
        self._resolution_producer = QueueProducer(RESOLUTION_STREAM)
        self._health = HealthStatus()

    async def handle_message(self, message: QueueMessage) -> None:
        msg = ExtractionMessage.model_validate(message.model_dump())
        set_correlation_id(msg.correlation_id)

        logger.info(
            "extraction_started",
            url=msg.url,
            record_type=msg.record_type,
            content_hash=msg.content_hash[:16],
        )

        # 1. Retrieve raw content from S3
        raw_content = await retrieve_raw_payload(msg.raw_s3_key)
        source_text = raw_content.decode("utf-8", errors="replace")

        # 2. LLM extraction
        extraction_result = await self._orchestrator.extract(
            html_content=source_text,
            record_type=msg.record_type,
            content_hash=msg.content_hash,
            source_url=msg.url,
        )

        if extraction_result.get("error"):
            logger.warning(
                "extraction_error",
                url=msg.url,
                error=extraction_result["error"],
            )
            raise RuntimeError(f"Extraction failed: {extraction_result['error']}")

        fields = extraction_result.get("fields", {})
        relationships = extraction_result.get("relationships", [])

        # 3. Ground every field against source text
        grounding_result = self._grounding_engine.verify_record(
            extracted_fields=fields,
            source_text=source_text,
            source_url=msg.url,
            content_hash=msg.content_hash,
        )

        # 4. Validate against JSON schema
        schema_valid, _schema_errors = validate_record(
            {"content": fields, "schemaVersion": "1.0", "recordType": msg.record_type,
             "source": {"url": msg.url, "fetchedAt": datetime.now(UTC).isoformat()}},
            msg.record_type,
        )

        # 5. Persist extraction state
        async with unit_of_work() as session:
            repo = CrawlItemRepository(session)
            await repo.update_state(
                msg.url,
                msg.source_name,
                "EXTRACTED" if grounding_result.is_exportable else "GROUNDING_FAILED",
                extracted_at=datetime.now(UTC),
            )

        # 6. Emit resolution message
        import json
        resolution_msg = ResolutionMessage(
            entity_id="",  # Will be assigned by resolver
            record_type=msg.record_type,
            entity_data=json.dumps({
                "fields": fields,
                "source_url": msg.url,
                "content_hash": msg.content_hash,
                "raw_s3_key": msg.raw_s3_key,
                "source_name": msg.source_name,
                "verification_status": grounding_result.verification_status.value,
                "grounding_ratio": grounding_result.grounding_ratio,
                "schema_valid": schema_valid,
            }),
            relationship_candidates=json.dumps(relationships),
            correlation_id=msg.correlation_id,
        )
        await self._resolution_producer.enqueue(resolution_msg)

        self._health.record_processed()
        logger.info(
            "extraction_completed",
            url=msg.url,
            provider=extraction_result.get("provider", ""),
            tokens=extraction_result.get("tokens", 0),
            grounding_status=grounding_result.verification_status.value,
            grounding_ratio=round(grounding_result.grounding_ratio, 2),
            schema_valid=schema_valid,
            cached=extraction_result.get("cached", False),
        )

    async def run(self, shutdown_event: asyncio.Event) -> None:
        consumer = QueueConsumer(
            stream=EXTRACTION_STREAM,
            group=EXTRACTION_CONSUMER_GROUP,
            consumer_name=self._worker_id,
            message_cls=ExtractionMessage,
            handler=self.handle_message,
            dlq_stream=EXTRACTION_DLQ,
        )
        self._health.set_ready()
        await consumer.run_loop(shutdown_event)

    async def close(self) -> None:
        await self._orchestrator.close()
