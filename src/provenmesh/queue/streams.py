"""Redis Streams wrapper — reliable message queue with consumer groups.

The pipeline uses Redis Streams for stage-to-stage communication (PDF §2).
Consumer groups provide at-least-once delivery with automatic message
acknowledgment after successful processing.
"""

from __future__ import annotations

import redis.asyncio as redis

from provenmesh.config.settings import get_settings
from provenmesh.observability.logging import get_logger
from provenmesh.observability.metrics import QUEUE_DEPTH

logger = get_logger(__name__)

_redis_pool: redis.Redis | None = None


async def get_redis() -> redis.Redis:
    """Get or create a shared Redis connection pool."""
    global _redis_pool  # noqa: PLW0603
    if _redis_pool is None:
        settings = get_settings()
        _redis_pool = redis.from_url(
            settings.redis_url,
            decode_responses=False,
            max_connections=20,
            socket_connect_timeout=5,
            socket_keepalive=True,
            retry_on_timeout=True,
        )
        # Verify connection
        await _redis_pool.ping()
        logger.info("redis_connected", url=settings.redis_url.split("@")[-1])
    return _redis_pool


async def close_redis() -> None:
    """Close the Redis connection pool."""
    global _redis_pool  # noqa: PLW0603
    if _redis_pool is not None:
        await _redis_pool.close()
        _redis_pool = None
        logger.info("redis_disconnected")


async def ensure_stream_and_group(
    stream: str,
    group: str,
) -> None:
    """Create a stream and consumer group if they don't exist.

    Uses MKSTREAM to create the stream atomically with the group.
    """
    r = await get_redis()
    try:
        await r.xgroup_create(stream, group, id="0", mkstream=True)
        logger.info("stream_group_created", stream=stream, group=group)
    except redis.ResponseError as e:
        if "BUSYGROUP" in str(e):
            # Group already exists — this is fine
            pass
        else:
            raise


async def get_stream_depth(stream: str) -> int:
    """Get current depth of a stream (for backpressure monitoring)."""
    r = await get_redis()
    try:
        length = await r.xlen(stream)
        QUEUE_DEPTH.labels(stream=stream).set(length)
        return length
    except Exception:
        return 0


async def add_to_stream(
    stream: str,
    data: dict[str, str],
    max_len: int = 100_000,
) -> str:
    """Add a message to a Redis Stream with automatic trimming.

    Returns the message ID assigned by Redis.
    """
    r = await get_redis()
    msg_id: bytes = await r.xadd(stream, data, maxlen=max_len, approximate=True)
    return msg_id.decode("utf-8") if isinstance(msg_id, bytes) else str(msg_id)


async def read_from_group(
    stream: str,
    group: str,
    consumer: str,
    count: int = 1,
    block_ms: int = 5000,
) -> list[tuple[str, dict[bytes, bytes]]]:
    """Read new messages from a consumer group.

    Uses XREADGROUP with blocking to efficiently wait for messages.
    Returns list of (message_id, field_dict) tuples.
    """
    r = await get_redis()
    result = await r.xreadgroup(
        group, consumer, {stream: ">"}, count=count, block=block_ms,
    )

    messages: list[tuple[str, dict[bytes, bytes]]] = []
    if result:
        for _stream_name, stream_messages in result:
            for msg_id, msg_data in stream_messages:
                mid = msg_id.decode("utf-8") if isinstance(msg_id, bytes) else str(msg_id)
                messages.append((mid, msg_data))

    return messages


async def ack_message(stream: str, group: str, message_id: str) -> None:
    """Acknowledge a message after successful processing.

    Critical: only call this AFTER the database transaction has committed
    (v2 §38: commit → ACK ordering prevents data loss).
    """
    r = await get_redis()
    await r.xack(stream, group, message_id)


async def claim_stale_messages(
    stream: str,
    group: str,
    consumer: str,
    min_idle_ms: int = 300_000,
    count: int = 10,
) -> list[tuple[str, dict[bytes, bytes]]]:
    """Claim messages that have been pending for too long (poison message protection).

    If a worker crashes, its messages stay in the pending entries list (PEL).
    Another worker can claim them after min_idle_ms (v2 hardening §5).
    """
    r = await get_redis()
    try:
        # First, get pending messages from all consumers
        pending = await r.xpending_range(
            stream, group, min="-", max="+", count=count,
        )

        claimed: list[tuple[str, dict[bytes, bytes]]] = []
        for entry in pending:
            msg_id = entry["message_id"]
            idle_time = entry["time_since_delivered"]

            if isinstance(msg_id, bytes):
                msg_id = msg_id.decode("utf-8")

            if idle_time >= min_idle_ms:
                # Claim the message
                result = await r.xclaim(
                    stream, group, consumer, min_idle_time=min_idle_ms,
                    message_ids=[msg_id],
                )
                for claimed_id, claimed_data in result:
                    cid = claimed_id.decode("utf-8") if isinstance(claimed_id, bytes) else str(claimed_id)
                    claimed.append((cid, claimed_data))
                    logger.warning(
                        "stale_message_claimed",
                        stream=stream,
                        message_id=msg_id,
                        idle_ms=idle_time,
                    )

        return claimed
    except Exception as e:
        logger.error("claim_stale_failed", stream=stream, error=str(e))
        return []
