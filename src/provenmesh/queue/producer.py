"""Queue producer — enqueues messages with backpressure control (v2 §1).

A producer never directly fetches the detail page (PDF §5.1).
It discovers listing pages and enqueues detail-page URLs to Redis Streams.
Backpressure pauses enqueuing when the downstream queue is full.
"""

from __future__ import annotations

import asyncio
import random
from typing import TYPE_CHECKING

from provenmesh.config.settings import get_settings
from provenmesh.observability.logging import get_logger
from provenmesh.queue.streams import add_to_stream, get_stream_depth

if TYPE_CHECKING:
    from provenmesh.queue.messages import QueueMessage

logger = get_logger(__name__)


class QueueProducer:
    """Producer with backpressure control.

    When the downstream queue exceeds HIGH_WATER_MARK, the producer
    sleeps with exponential backoff. When it drops below LOW_WATER_MARK,
    normal enqueuing resumes.

    This matches the PDF's backpressure design (§3.2):
    "if the LLM orchestrator's input queue exceeds a threshold,
    scraper workers pause enqueuing."
    """

    def __init__(self, stream: str) -> None:
        self._stream = stream
        self._settings = get_settings()
        self._backoff_count = 0
        self._backpressure_active = False
        self._messages_produced = 0

    async def enqueue(self, message: QueueMessage) -> str:
        """Enqueue a message with backpressure check.

        Returns the Redis Stream message ID.
        """
        await self._check_backpressure()

        msg_id = await add_to_stream(self._stream, message.to_stream_data())
        self._messages_produced += 1

        logger.debug(
            "message_enqueued",
            stream=self._stream,
            message_id=msg_id,
            total_produced=self._messages_produced,
        )

        return msg_id

    async def enqueue_batch(self, messages: list[QueueMessage]) -> list[str]:
        """Enqueue multiple messages, respecting backpressure."""
        ids: list[str] = []
        for msg in messages:
            msg_id = await self.enqueue(msg)
            ids.append(msg_id)
        return ids

    async def _check_backpressure(self) -> None:
        """Apply backpressure when queue depth exceeds high water mark.

        Implements exponential backoff with jitter to prevent producer
        thundering herd when backpressure releases.
        """
        depth = await get_stream_depth(self._stream)

        if depth >= self._settings.queue_high_water_mark:
            if not self._backpressure_active:
                self._backpressure_active = True
                logger.warning(
                    "backpressure_activated",
                    stream=self._stream,
                    depth=depth,
                    high_water_mark=self._settings.queue_high_water_mark,
                )

            # Exponential backoff with jitter
            delay = min(
                2 ** self._backoff_count + random.uniform(0, 1.0),  # noqa: S311
                self._settings.backpressure_max_delay_seconds,
            )
            self._backoff_count += 1
            await asyncio.sleep(delay)

        elif depth <= self._settings.queue_low_water_mark:
            if self._backpressure_active:
                self._backpressure_active = False
                self._backoff_count = 0
                logger.info(
                    "backpressure_released",
                    stream=self._stream,
                    depth=depth,
                    low_water_mark=self._settings.queue_low_water_mark,
                )
