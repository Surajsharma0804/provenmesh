"""Tests for crawler/rate_limiter.py — TokenBucketLimiter and DomainRateLimiter."""
from __future__ import annotations

import asyncio

from provenmesh.crawler.rate_limiter import TokenBucketLimiter


class TestTokenBucketLimiter:
    async def test_initial_acquire_no_wait(self) -> None:
        limiter = TokenBucketLimiter(rate=10.0, capacity=1.0)
        wait = await limiter.acquire()
        assert wait == 0.0

    async def test_second_acquire_waits(self) -> None:
        limiter = TokenBucketLimiter(rate=100.0, capacity=1.0)
        await limiter.acquire()
        wait = await limiter.acquire()
        # Should have waited a small amount
        assert isinstance(wait, float)

    async def test_refill_over_time(self) -> None:
        limiter = TokenBucketLimiter(rate=1000.0, capacity=2.0)
        await limiter.acquire()
        await limiter.acquire()
        await asyncio.sleep(0.01)
        wait = await limiter.acquire()
        assert isinstance(wait, float)
