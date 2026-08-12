"""Crawl worker — fetches pages, stores raw evidence, emits extraction messages.

Transaction boundary (v2 §38):
    fetch → dedup → store S3 → DB crawl_item → emit extraction msg → ACK
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from provenmesh.config.constants import (
    CRAWL_CONSUMER_GROUP,
    CRAWL_DLQ,
    DISCOVERY_STREAM,
    EXTRACTION_STREAM,
)
from provenmesh.crawler.dedup import check_content_seen, compute_content_hash
from provenmesh.crawler.fetcher import TieredFetcher
from provenmesh.domain.evidence import CrawlManifest
from provenmesh.graph.repository import CrawlItemRepository
from provenmesh.observability.health import HealthStatus
from provenmesh.observability.logging import get_logger, set_correlation_id
from provenmesh.queue.consumer import QueueConsumer
from provenmesh.queue.messages import CrawlMessage, ExtractionMessage, QueueMessage
from provenmesh.queue.producer import QueueProducer
from provenmesh.raw_store.s3 import store_raw_payload
from provenmesh.storage.transactions import unit_of_work

if TYPE_CHECKING:
    import asyncio

logger = get_logger(__name__)


class CrawlWorker:
    """Fetches pages and stores raw evidence.

    This is a stateless consumer — safe to scale horizontally.
    Idempotency: content-hash dedup prevents re-extraction of
    unchanged pages.
    """

    def __init__(self, worker_id: str = "crawl-0") -> None:
        self._worker_id = worker_id
        self._fetcher = TieredFetcher()
        self._extraction_producer = QueueProducer(EXTRACTION_STREAM)
        self._health = HealthStatus()

    async def handle_message(self, message: QueueMessage) -> None:
        """Process a single crawl message."""
        msg = CrawlMessage.model_validate(message.model_dump())
        set_correlation_id(msg.correlation_id)

        logger.info(
            "crawl_started",
            url=msg.url,
            source=msg.source_name,
            tier=msg.fetch_tier,
        )

        # Fetch the page
        result = await self._fetcher.fetch(
            msg.url,
            source_name=msg.source_name,
            record_type=msg.record_type,
            max_tier=msg.fetch_tier,
        )

        if not result.ok:
            logger.warning("fetch_failed", url=msg.url, status=result.status, error=result.error)
            # Update state and let retry/DLQ handle it
            async with unit_of_work() as session:
                repo = CrawlItemRepository(session)
                await repo.update_state(
                    msg.url, msg.source_name, "FETCH_FAILED",
                    last_error=result.error or f"HTTP {result.status}",
                    attempt_count=msg.attempt + 1,
                )
            raise RuntimeError(f"Fetch failed: {result.error or result.status}")

        # Compute content hash
        content_hash = compute_content_hash(result.content)

        # Content-level dedup (same URL, unchanged content)
        if await check_content_seen(content_hash, msg.source_name):
            logger.info("content_unchanged", url=msg.url, hash=content_hash[:16])
            return

        # Store raw payload to S3
        manifest = CrawlManifest(
            url=msg.url,
            source_name=msg.source_name,
            status_code=result.status,
            content_type=result.content_type,
            content_hash=content_hash,
            content_length=len(result.content),
            fetch_tier=result.fetch_tier,
            encoding=result.encoding,
            headers=result.headers,
            correlation_id=msg.correlation_id,
        )
        s3_key = await store_raw_payload(result.content, manifest)

        # Persist crawl state to DB
        async with unit_of_work() as session:
            repo = CrawlItemRepository(session)
            await repo.update_state(
                msg.url,
                msg.source_name,
                "FETCHED",
                content_hash=content_hash,
                raw_s3_key=s3_key,
                fetch_tier=result.fetch_tier,
                status_code=result.status,
                fetched_at=datetime.now(UTC),
            )

        # Emit extraction message
        extraction_msg = ExtractionMessage(
            url=msg.url,
            source_name=msg.source_name,
            record_type=msg.record_type,
            content_hash=content_hash,
            raw_s3_key=s3_key,
            content_length=len(result.content),
            correlation_id=msg.correlation_id,
        )
        await self._extraction_producer.enqueue(extraction_msg)

        self._health.record_processed()
        logger.info(
            "crawl_completed",
            url=msg.url,
            content_hash=content_hash[:16],
            s3_key=s3_key,
            tier=result.fetch_tier,
            elapsed_ms=round(result.elapsed_ms, 1),
        )

    async def run(self, shutdown_event: asyncio.Event) -> None:
        """Main worker loop."""
        consumer = QueueConsumer(
            stream=DISCOVERY_STREAM,
            group=CRAWL_CONSUMER_GROUP,
            consumer_name=self._worker_id,
            message_cls=CrawlMessage,
            handler=self.handle_message,
            dlq_stream=CRAWL_DLQ,
        )
        self._health.set_ready()
        await consumer.run_loop(shutdown_event)
