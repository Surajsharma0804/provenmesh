"""Rate limiter — per-domain and global concurrency control (PDF §7.2, v2 §7).

Two levels:
    1. Global: MAX_GLOBAL_CONCURRENCY across all domains
    2. Per-domain: configurable requests/sec + concurrency cap

The PDF's baseline is 1 req/sec/domain so horizontal scaling
increases coverage breadth, not load on any single target.
"""

from __future__ import annotations

import asyncio
import time

from provenmesh.config.settings import get_settings
from provenmesh.observability.logging import get_logger

logger = get_logger(__name__)


class TokenBucketLimiter:
    """Token bucket rate limiter for per-domain request rate control.

    Refills at `rate` tokens per second, up to `capacity`.
    Each request consumes one token. If no tokens, wait.
    """

    def __init__(self, rate: float, capacity: float = 1.0) -> None:
        self._rate = rate
        self._capacity = capacity
        self._tokens = capacity
        self._last_refill = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self) -> float:
        """Wait until a token is available. Returns wait time in seconds."""
        async with self._lock:
            now = time.monotonic()
            elapsed = now - self._last_refill
            self._tokens = min(self._capacity, self._tokens + elapsed * self._rate)
            self._last_refill = now

            if self._tokens >= 1.0:
                self._tokens -= 1.0
                return 0.0

            # Need to wait for token refill
            wait_time = (1.0 - self._tokens) / self._rate
            self._tokens = 0.0
            await asyncio.sleep(wait_time)
            self._last_refill = time.monotonic()
            return wait_time


class DomainRateLimiter:
    """Per-domain rate limiting with configurable overrides (v2 §7).

    Maintains a token bucket and a concurrency semaphore per domain.
    Domain-specific overrides from sources.yaml take priority.
    """

    def __init__(self) -> None:
        self._settings = get_settings()
        self._limiters: dict[str, TokenBucketLimiter] = {}
        self._semaphores: dict[str, asyncio.Semaphore] = {}
        self._global_semaphore = asyncio.Semaphore(self._settings.max_global_concurrency)
        self._domain_overrides: dict[str, dict[str, float]] = {}
        self._lock = asyncio.Lock()

    def set_domain_override(
        self,
        domain: str,
        requests_per_second: float | None = None,
        max_concurrency: int | None = None,
    ) -> None:
        """Set custom rate limits for a specific domain."""
        self._domain_overrides[domain] = {}
        if requests_per_second is not None:
            self._domain_overrides[domain]["rps"] = requests_per_second
        if max_concurrency is not None:
            self._domain_overrides[domain]["concurrency"] = float(max_concurrency)

    def _get_limiter(self, domain: str) -> TokenBucketLimiter:
        """Get or create a rate limiter for a domain."""
        if domain not in self._limiters:
            overrides = self._domain_overrides.get(domain, {})
            rps = overrides.get("rps", self._settings.per_domain_rate_limit_rps)
            self._limiters[domain] = TokenBucketLimiter(rate=rps, capacity=max(rps, 1.0))
        return self._limiters[domain]

    def _get_semaphore(self, domain: str) -> asyncio.Semaphore:
        """Get or create a concurrency semaphore for a domain."""
        if domain not in self._semaphores:
            overrides = self._domain_overrides.get(domain, {})
            concurrency = int(overrides.get("concurrency", self._settings.max_domain_concurrency))
            self._semaphores[domain] = asyncio.Semaphore(concurrency)
        return self._semaphores[domain]

    async def acquire(self, domain: str) -> None:
        """Acquire both rate limit token and concurrency slot for a domain.

        Blocks until both are available. Respects both per-domain
        and global limits simultaneously.
        """
        limiter = self._get_limiter(domain)
        domain_sem = self._get_semaphore(domain)

        # Acquire global concurrency first, then domain
        await self._global_semaphore.acquire()
        try:
            await domain_sem.acquire()
            wait_time = await limiter.acquire()
            if wait_time > 0:
                logger.debug(
                    "rate_limit_wait",
                    domain=domain,
                    wait_seconds=round(wait_time, 3),
                )
        except Exception:
            self._global_semaphore.release()
            raise

    def release(self, domain: str) -> None:
        """Release concurrency slots after request completes."""
        domain_sem = self._get_semaphore(domain)
        domain_sem.release()
        self._global_semaphore.release()


# Module-level singleton
_rate_limiter: DomainRateLimiter | None = None


def get_rate_limiter() -> DomainRateLimiter:
    """Get the global rate limiter singleton."""
    global _rate_limiter
    if _rate_limiter is None:
        _rate_limiter = DomainRateLimiter()
    return _rate_limiter
