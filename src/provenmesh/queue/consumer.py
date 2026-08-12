"""Queue consumer — reads from Redis Streams with retry and DLQ routing."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Coroutine
from typing import Any

from provenmesh.config.settings import get_settings
from provenmesh.observability.logging import get_logger, set_correlation_id
from provenmesh.queue.dlq import route_to_dlq
from provenmesh.queue.messages import QueueMessage
from provenmesh.queue.streams import (
    ack_message,
    claim_stale_messages,
    ensure_stream_and_group,
    read_from_group,
)

logger = get_logger(__name__)

MessageHandler = Callable[[QueueMessage], Coroutine[Any, Any, None]]


class QueueConsumer:
    """Reliable queue consumer with retry logic and DLQ routing.

    Transaction boundary (v2 §38):
        process message → DB transaction → commit → ACK queue

    If DB transaction fails → no ACK → message retried.
    If max attempts exceeded → route to DLQ.
    """

    def __init__(
        self,
        stream: str,
        group: str,
        consumer_name: str,
        message_cls: type[QueueMessage],
        handler: MessageHandler,
        *,
        dlq_stream: str = "",
        batch_size: int = 1,
        block_ms: int = 5000,
    ) -> None:
        self._stream = stream
        self._group = group
        self._consumer_name = consumer_name
        self._message_cls = message_cls
        self._handler = handler
        self._dlq_stream = dlq_stream
        self._batch_size = batch_size
        self._block_ms = block_ms
        self._running = False
        self._items_processed = 0

        self._settings = get_settings()

    async def start(self) -> None:
        """Initialize the consumer group and start processing."""
        await ensure_stream_and_group(self._stream, self._group)
        if self._dlq_stream:
            await ensure_stream_and_group(self._dlq_stream, f"{self._group}-dlq")
        self._running = True

        logger.info(
            "consumer_started",
            stream=self._stream,
            group=self._group,
            consumer=self._consumer_name,
        )

    async def stop(self) -> None:
        """Gracefully stop the consumer."""
        self._running = False
        logger.info(
            "consumer_stopping",
            stream=self._stream,
            items_processed=self._items_processed,
        )

    async def process_batch(self) -> int:
        """Process a single batch of messages. Returns count processed."""
        if not self._running:
            return 0

        # First, try to claim any stale messages (poison message protection)
        stale = await claim_stale_messages(
            self._stream,
            self._group,
            self._consumer_name,
            min_idle_ms=self._settings.poison_message_max_idle_ms,
            count=1,
        )
        for msg_id, msg_data in stale:
            await self._process_single(msg_id, msg_data, is_reclaimed=True)

        # Then read new messages
        messages = await read_from_group(
            self._stream,
            self._group,
            self._consumer_name,
            count=self._batch_size,
            block_ms=self._block_ms,
        )

        for msg_id, msg_data in messages:
            await self._process_single(msg_id, msg_data, is_reclaimed=False)

        return len(messages) + len(stale)

    async def _process_single(
        self,
        msg_id: str,
        msg_data: dict[bytes, bytes],
        *,
        is_reclaimed: bool = False,
    ) -> None:
        """Process a single message with retry and DLQ routing."""
        try:
            message = self._message_cls.from_stream_data(msg_data)
            set_correlation_id(message.correlation_id)

            if is_reclaimed:
                message.attempt += 1
                logger.warning(
                    "processing_reclaimed_message",
                    message_id=msg_id,
                    attempt=message.attempt,
                )

            # Check if max attempts exceeded
            if message.attempt >= message.max_attempts:
                logger.error(
                    "max_attempts_exceeded",
                    message_id=msg_id,
                    attempts=message.attempt,
                )
                if self._dlq_stream:
                    await route_to_dlq(
                        self._dlq_stream,
                        message,
                        stage=self._stream,
                        error=RuntimeError("Max attempts exceeded"),
                    )
                await ack_message(self._stream, self._group, msg_id)
                return

            # Process the message
            await self._handler(message)

            # Only ACK after successful processing (v2 §38)
            await ack_message(self._stream, self._group, msg_id)
            self._items_processed += 1

        except Exception as e:
            logger.error(
                "message_processing_failed",
                message_id=msg_id,
                error=str(e),
                error_type=type(e).__name__,
            )
            # Don't ACK — message will be retried via pending entries
            # If it's been pending too long, claim_stale_messages will pick it up

    async def run_loop(self, shutdown_event: asyncio.Event) -> None:
        """Main processing loop — runs until shutdown event is set."""
        await self.start()

        while not shutdown_event.is_set():
            try:
                processed = await self.process_batch()

                # Worker recycling (hardening §8)
                if self._items_processed >= self._settings.worker_max_items_before_recycle:
                    logger.info(
                        "worker_recycling",
                        items_processed=self._items_processed,
                        max_items=self._settings.worker_max_items_before_recycle,
                    )
                    break

            except Exception as e:
                logger.error("consumer_loop_error", error=str(e))
                await asyncio.sleep(1)

        await self.stop()
