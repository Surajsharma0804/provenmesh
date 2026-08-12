"""Base producer — abstract listing page enumerator (PDF §3.2, v2 §5.1).

A producer NEVER directly fetches detail pages. It discovers listing
pages and enqueues detail-page URLs to Redis Streams. This keeps
fan-out decoupled from fan-in.

Checkpointing (PDF §10.2, v2 §36):
    After every successfully processed listing page, the producer persists
    its cursor to Redis. On restart, it resumes from the last checkpoint.
"""

from __future__ import annotations

import abc
import json
from typing import Any

from provenmesh.config.constants import DISCOVERY_STREAM
from provenmesh.crawler.dedup import is_duplicate
from provenmesh.crawler.normalization import normalize_url
from provenmesh.observability.logging import get_logger, new_correlation_id
from provenmesh.observability.metrics import CRAWL_ITEMS_TOTAL
from provenmesh.queue.messages import CrawlMessage
from provenmesh.queue.producer import QueueProducer
from provenmesh.queue.streams import get_redis

logger = get_logger(__name__)


class BaseProducer(abc.ABC):
    """Abstract base for all vertical producers.

    Subclasses implement:
        - `vertical_name`: The vertical identifier.
        - `discover_urls()`: Enumerate listing pages and yield detail URLs.
        - `parse_listing_page()`: Extract detail URLs from a listing page.
    """

    def __init__(self) -> None:
        self._producer = QueueProducer(DISCOVERY_STREAM)
        self._checkpoint_prefix = "checkpoint"
        self._urls_discovered = 0

    @property
    @abc.abstractmethod
    def vertical_name(self) -> str:
        """Vertical identifier (e.g., 'startups', 'papers')."""
        ...

    @property
    @abc.abstractmethod
    def record_type(self) -> str:
        """Record type enum value (e.g., 'STARTUP', 'PAPER')."""
        ...

    @abc.abstractmethod
    async def discover_urls(self) -> None:
        """Enumerate listing pages and enqueue discovered detail URLs.

        This is the main entry point. Implementations should:
            1. Load checkpoint (last processed page)
            2. Iterate through listing pages
            3. Extract detail URLs from each page
            4. Dedup-check each URL
            5. Enqueue new URLs via self._enqueue_url()
            6. Save checkpoint after each page
        """
        ...

    async def _enqueue_url(
        self,
        url: str,
        source_name: str,
        *,
        listing_page: int = 0,
        fetch_tier: int = 1,
        title: str = "",
    ) -> bool:
        """Enqueue a discovered URL after dedup check.

        Returns True if the URL was enqueued (new), False if duplicate.
        """
        normalized = normalize_url(url)
        if not normalized:
            return False

        # Dedup check (layer 1: Redis)
        if await is_duplicate(normalized, title=title, source_name=source_name):
            return False

        correlation_id = new_correlation_id()

        message = CrawlMessage(
            url=normalized,
            source_name=source_name,
            record_type=self.record_type,
            listing_page=listing_page,
            fetch_tier=fetch_tier,
            correlation_id=correlation_id,
        )

        await self._producer.enqueue(message)
        self._urls_discovered += 1
        CRAWL_ITEMS_TOTAL.labels(
            vertical=self.vertical_name,
            source_name=source_name,
        ).inc()

        return True

    async def _save_checkpoint(
        self,
        source_name: str,
        page: int,
        last_url: str = "",
    ) -> None:
        """Save producer checkpoint to Redis (PDF §10.2).

        On restart, the producer resumes from this checkpoint instead
        of re-walking from page 1.
        """
        r = await get_redis()
        key = f"{self._checkpoint_prefix}:{self.vertical_name}:{source_name}"
        data = json.dumps({
            "page": page,
            "last_url": last_url,
            "urls_discovered": self._urls_discovered,
        })
        await r.set(key, data)
        logger.debug(
            "checkpoint_saved",
            vertical=self.vertical_name,
            source=source_name,
            page=page,
        )

    async def _load_checkpoint(self, source_name: str) -> dict[str, Any]:
        """Load the last checkpoint for a source."""
        r = await get_redis()
        key = f"{self._checkpoint_prefix}:{self.vertical_name}:{source_name}"
        data = await r.get(key)
        if data:
            return json.loads(data)
        return {"page": 0, "last_url": "", "urls_discovered": 0}

    async def run(self) -> int:
        """Execute the producer. Returns total URLs discovered."""
        logger.info(
            "producer_started",
            vertical=self.vertical_name,
        )

        try:
            await self.discover_urls()
        except Exception as e:
            logger.error(
                "producer_failed",
                vertical=self.vertical_name,
                error=str(e),
            )
            raise

        logger.info(
            "producer_completed",
            vertical=self.vertical_name,
            urls_discovered=self._urls_discovered,
        )

        return self._urls_discovered
