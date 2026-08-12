"""Tiered fetcher — the main fetch orchestrator (PDF §7.1, v2 §6).

Escalation path:
    robots allowed? → Tier 1 aiohttp → Tier 2 Playwright → Tier 3 Playwright+Proxy → DLQ

Before EVERY escalation: robots.txt + rate limit + source policy.
If the site disallows crawling: DO NOT ESCALATE (PDF §7.2).

Retry-After header parsing (hardening §4):
    Honors Retry-After from 429 responses for faster and more polite backoff.
"""

from __future__ import annotations

import asyncio
import random
import time

from provenmesh.config.settings import get_settings
from provenmesh.crawler.browser import fetch_with_browser
from provenmesh.crawler.http_client import FetchResult, fetch_url
from provenmesh.crawler.normalization import extract_domain
from provenmesh.crawler.proxy import get_proxy_pool
from provenmesh.crawler.rate_limiter import get_rate_limiter
from provenmesh.crawler.robots import get_robots_checker
from provenmesh.observability.logging import get_logger
from provenmesh.observability.metrics import (
    CRAWL_FAILURE_TOTAL,
    CRAWL_SUCCESS_TOTAL,
    FETCH_TIER_TOTAL,
)

logger = get_logger(__name__)


class TieredFetcher:
    """Fetches URLs using the cheapest method that works.

    Escalation is automatic on failure, but always gated by:
        1. robots.txt compliance
        2. Rate limiting
        3. Per-domain policy
    """

    def __init__(self) -> None:
        self._settings = get_settings()
        self._robots = get_robots_checker()
        self._rate_limiter = get_rate_limiter()

    async def fetch(
        self,
        url: str,
        source_name: str = "",
        record_type: str = "",
        *,
        max_tier: int = 3,
        retry_count: int = 0,
    ) -> FetchResult:
        """Fetch a URL using tiered escalation.

        Args:
            url: The URL to fetch.
            source_name: Name of the data source (for metrics).
            record_type: Entity type (for metrics).
            max_tier: Maximum tier to escalate to (1, 2, or 3).
            retry_count: Current retry attempt number.

        Returns:
            FetchResult with content or error details.
        """
        domain = extract_domain(url)

        # Gate 1: robots.txt compliance (PDF §7.2)
        if not await self._robots.is_allowed(url):
            logger.info("fetch_blocked_by_robots", url=url, domain=domain)
            return FetchResult(url=url, error="blocked_by_robots", fetch_tier=0)

        # Gate 2: Rate limiting
        await self._rate_limiter.acquire(domain)
        try:
            # Respect Crawl-delay
            crawl_delay = await self._robots.get_crawl_delay(url)
            if crawl_delay > 0:
                await asyncio.sleep(crawl_delay)

            # Tier 1: aiohttp
            FETCH_TIER_TOTAL.labels(tier="1").inc()
            result = await fetch_url(url)
            if result.ok:
                CRAWL_SUCCESS_TOTAL.labels(
                    vertical=record_type, source_name=source_name, fetch_tier="1",
                ).inc()
                return result

            # Handle Retry-After on 429 (hardening §4)
            if result.is_rate_limited:
                retry_after = result.headers.get("Retry-After", "")
                if retry_after:
                    try:
                        delay = float(retry_after) + random.uniform(0, 1.0)
                    except ValueError:
                        delay = 2 ** retry_count + random.uniform(0, 1.5)
                else:
                    delay = 2 ** retry_count + random.uniform(0, 1.5)
                delay = min(delay, 60.0)
                logger.info("rate_limited_waiting", url=url, delay=delay)
                await asyncio.sleep(delay)

            # Tier 2: Playwright (if allowed)
            if max_tier >= 2 and not result.ok:
                FETCH_TIER_TOTAL.labels(tier="2").inc()
                result = await fetch_with_browser(url)
                if result.ok:
                    CRAWL_SUCCESS_TOTAL.labels(
                        vertical=record_type, source_name=source_name, fetch_tier="2",
                    ).inc()
                    return result

            # Tier 3: Playwright + Proxy (if allowed and proxy available)
            if max_tier >= 3 and not result.ok:
                pool = get_proxy_pool()
                proxy = pool.get_proxy(domain)
                if proxy:
                    FETCH_TIER_TOTAL.labels(tier="3").inc()
                    result = await fetch_with_browser(url)
                    if result.ok:
                        pool.record_success(proxy)
                        CRAWL_SUCCESS_TOTAL.labels(
                            vertical=record_type, source_name=source_name, fetch_tier="3",
                        ).inc()
                        return result
                    else:
                        pool.record_failure(proxy, domain)

            # All tiers failed
            if not result.ok:
                CRAWL_FAILURE_TOTAL.labels(
                    vertical=record_type,
                    source_name=source_name,
                    error_type=result.error or f"http_{result.status}",
                ).inc()
                logger.warning(
                    "all_tiers_exhausted",
                    url=url,
                    last_status=result.status,
                    last_error=result.error,
                )

            return result

        finally:
            self._rate_limiter.release(domain)
