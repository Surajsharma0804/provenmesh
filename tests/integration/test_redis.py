"""Integration tests — Redis Streams, dedup, and queue operations (v2 §41).

Requires a running Redis instance (Docker Compose or CI service container).
Mark: @pytest.mark.integration
"""

from __future__ import annotations

import asyncio
import os

import pytest

# Skip entire module if Redis is unavailable
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")


@pytest.fixture
async def redis_client():
    """Provide a clean Redis connection for each test."""
    import redis.asyncio as aioredis

    client = aioredis.from_url(REDIS_URL, decode_responses=True)
    try:
        await client.ping()
    except Exception:
        pytest.skip("Redis not available")

    # Clean test keys before each test
    test_keys = await client.keys("test:*")
    if test_keys:
        await client.delete(*test_keys)

    yield client
    await client.aclose()


@pytest.mark.integration
class TestRedisStreams:
    """Test Redis Streams producer/consumer operations."""

    async def test_xadd_and_xread(self, redis_client):
        """Verify basic stream write and read."""
        stream = "test:stream:basic"
        msg_id = await redis_client.xadd(stream, {"url": "https://example.com", "type": "STARTUP"})
        assert msg_id is not None

        messages = await redis_client.xread({stream: "0"}, count=1)
        assert len(messages) == 1
        assert messages[0][1][0][1]["url"] == "https://example.com"

        await redis_client.delete(stream)

    async def test_consumer_group_creation(self, redis_client):
        """Verify consumer group creation and assignment."""
        stream = "test:stream:groups"
        await redis_client.xadd(stream, {"data": "test"})

        # Create consumer group
        await redis_client.xgroup_create(stream, "test-group", id="0", mkstream=True)

        # Read as consumer
        messages = await redis_client.xreadgroup(
            "test-group", "consumer-1", {stream: ">"}, count=1
        )
        assert len(messages) == 1

        # ACK the message
        msg_id = messages[0][1][0][0]
        acked = await redis_client.xack(stream, "test-group", msg_id)
        assert acked == 1

        await redis_client.delete(stream)

    async def test_xlen_tracks_stream_depth(self, redis_client):
        """Verify stream depth tracking for backpressure monitoring."""
        stream = "test:stream:depth"
        for i in range(10):
            await redis_client.xadd(stream, {"item": str(i)})

        length = await redis_client.xlen(stream)
        assert length == 10

        await redis_client.delete(stream)


@pytest.mark.integration
class TestRedisDedup:
    """Test distributed deduplication with Redis SADD."""

    async def test_sadd_dedup_new_item(self, redis_client):
        """New item should be added successfully."""
        key = "test:dedup:2026-08-12"
        added = await redis_client.sadd(key, "hash_abc123")
        assert added == 1

        await redis_client.delete(key)

    async def test_sadd_dedup_duplicate(self, redis_client):
        """Duplicate item should return 0 (already exists)."""
        key = "test:dedup:2026-08-12"
        await redis_client.sadd(key, "hash_abc123")
        added_again = await redis_client.sadd(key, "hash_abc123")
        assert added_again == 0

        await redis_client.delete(key)

    async def test_dedup_with_date_bucketing(self, redis_client):
        """Same hash in different date buckets should both succeed."""
        key1 = "test:dedup:2026-08-11"
        key2 = "test:dedup:2026-08-12"

        added1 = await redis_client.sadd(key1, "hash_same")
        added2 = await redis_client.sadd(key2, "hash_same")
        assert added1 == 1
        assert added2 == 1

        await redis_client.delete(key1, key2)

    async def test_dedup_ttl_expiry(self, redis_client):
        """Dedup keys should support TTL for bounded memory."""
        key = "test:dedup:ttl"
        await redis_client.sadd(key, "hash_temp")
        await redis_client.expire(key, 2)

        assert await redis_client.sismember(key, "hash_temp")
        await asyncio.sleep(3)
        assert not await redis_client.sismember(key, "hash_temp")


@pytest.mark.integration
class TestRedisCircuitBreaker:
    """Test circuit breaker state tracking in Redis."""

    async def test_circuit_state_transitions(self, redis_client):
        """Verify circuit breaker state tracking."""
        key = "test:circuit:gemini"

        # Start CLOSED
        await redis_client.hset(key, mapping={"state": "CLOSED", "failures": "0"})
        state = await redis_client.hget(key, "state")
        assert state == "CLOSED"

        # Increment failures
        for _ in range(5):
            await redis_client.hincrby(key, "failures", 1)

        failures = int(await redis_client.hget(key, "failures"))
        assert failures == 5

        # Trip to OPEN
        await redis_client.hset(key, "state", "OPEN")
        state = await redis_client.hget(key, "state")
        assert state == "OPEN"

        await redis_client.delete(key)
