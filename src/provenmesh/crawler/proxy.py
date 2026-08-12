"""Proxy rotation — Tier 3 fetching support (PDF §7.1).

Sticky-per-domain with fallback (hardening §10):
    - Same proxy for the same domain within a session
    - Rotate to next proxy on failure
    - Track per-proxy success rate, deprioritize failing proxies
"""

from __future__ import annotations

import random
from collections import defaultdict
from dataclasses import dataclass, field

from provenmesh.config.settings import get_settings
from provenmesh.observability.logging import get_logger

logger = get_logger(__name__)


@dataclass
class ProxyStats:
    """Track success/failure rate for a proxy."""

    successes: int = 0
    failures: int = 0

    @property
    def total(self) -> int:
        return self.successes + self.failures

    @property
    def success_rate(self) -> float:
        if self.total == 0:
            return 1.0
        return self.successes / self.total


@dataclass
class ProxyPool:
    """Manages a pool of proxies with sticky-per-domain assignment and health tracking.

    Reserved for Cloudflare/Datadome-fronted high-value sources,
    with a per-domain concurrency cap of 1-2 (PDF §7.1).
    """

    proxies: list[str] = field(default_factory=list)
    _stats: dict[str, ProxyStats] = field(default_factory=lambda: defaultdict(ProxyStats))
    _domain_assignments: dict[str, str] = field(default_factory=dict)
    _min_success_rate: float = 0.3

    def add_proxy(self, proxy_url: str) -> None:
        """Add a proxy to the pool."""
        if proxy_url and proxy_url not in self.proxies:
            self.proxies.append(proxy_url)

    def get_proxy(self, domain: str) -> str | None:
        """Get a proxy for a domain (sticky assignment).

        Returns the same proxy for repeat requests to the same domain
        to avoid suspicious IP hopping (hardening §10).
        """
        if not self.proxies:
            return None

        # Check existing sticky assignment
        if domain in self._domain_assignments:
            proxy = self._domain_assignments[domain]
            if self._stats[proxy].success_rate >= self._min_success_rate:
                return proxy
            # Proxy is failing — rotate
            del self._domain_assignments[domain]

        # Select best proxy (highest success rate)
        available = sorted(
            self.proxies,
            key=lambda p: self._stats[p].success_rate,
            reverse=True,
        )

        # Add some randomness among the top proxies
        top_n = min(3, len(available))
        proxy = random.choice(available[:top_n])

        self._domain_assignments[domain] = proxy
        return proxy

    def record_success(self, proxy: str) -> None:
        """Record a successful request through this proxy."""
        self._stats[proxy].successes += 1

    def record_failure(self, proxy: str, domain: str) -> None:
        """Record a failed request — may trigger rotation."""
        self._stats[proxy].failures += 1

        if self._stats[proxy].success_rate < self._min_success_rate:
            logger.warning(
                "proxy_deprioritized",
                proxy=proxy[:20] + "...",
                success_rate=round(self._stats[proxy].success_rate, 2),
            )
            # Remove sticky assignment so next request rotates
            self._domain_assignments.pop(domain, None)

    def get_stats(self) -> dict[str, dict[str, float]]:
        """Get stats summary for all proxies."""
        return {
            p[:20] + "...": {
                "success_rate": round(self._stats[p].success_rate, 2),
                "total_requests": self._stats[p].total,
            }
            for p in self.proxies
        }


# Module-level singleton
_proxy_pool: ProxyPool | None = None


def get_proxy_pool() -> ProxyPool:
    """Get or initialize the proxy pool."""
    global _proxy_pool  # noqa: PLW0603
    if _proxy_pool is None:
        _proxy_pool = ProxyPool()
        settings = get_settings()
        if settings.proxy_pool_url:
            _proxy_pool.add_proxy(settings.proxy_pool_url)
    return _proxy_pool
