"""robots.txt enforcement — ethical scraping posture (PDF §7.2).

Before any Tier 2/3 escalation, the crawler checks robots.txt and
honors Crawl-delay where present; disallowed paths are skipped,
not bypassed. This module is the compliance gate.
"""

from __future__ import annotations

import asyncio
import time
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import aiohttp

from provenmesh.config.constants import USER_AGENTS
from provenmesh.observability.logging import get_logger

logger = get_logger(__name__)


class RobotsChecker:
    """Async robots.txt parser and enforcer.

    Caches parsed robots.txt per domain for 1 hour.
    Respects Crawl-delay directives.
    """

    def __init__(self) -> None:
        self._parsers: dict[str, RobotFileParser] = {}
        self._crawl_delays: dict[str, float] = {}
        self._cache_timestamps: dict[str, float] = {}
        self._cache_ttl = 3600  # 1 hour
        self._lock = asyncio.Lock()

    async def is_allowed(self, url: str, user_agent: str = "*") -> bool:
        """Check if a URL is allowed by robots.txt.

        Returns True if allowed, False if disallowed.
        If robots.txt cannot be fetched, defaults to allowed (standard behavior).
        """
        parsed = urlparse(url)
        domain = f"{parsed.scheme}://{parsed.netloc}"

        parser = await self._get_parser(domain)
        if parser is None:
            return True  # Cannot fetch robots.txt → assume allowed

        return parser.can_fetch(user_agent, url)

    async def get_crawl_delay(self, url: str, user_agent: str = "*") -> float:
        """Get Crawl-delay for a domain, or 0 if not specified."""
        parsed = urlparse(url)
        domain = f"{parsed.scheme}://{parsed.netloc}"

        parser = await self._get_parser(domain)
        if parser is None:
            return 0.0

        delay = parser.crawl_delay(user_agent)
        if delay is not None:
            return float(delay)
        return 0.0

    async def _get_parser(self, domain: str) -> RobotFileParser | None:
        """Get or fetch the robots.txt parser for a domain."""
        async with self._lock:
            now = time.monotonic()

            # Check cache
            if domain in self._parsers:
                cache_age = now - self._cache_timestamps.get(domain, 0)
                if cache_age < self._cache_ttl:
                    return self._parsers[domain]

            # Fetch robots.txt
            robots_url = f"{domain}/robots.txt"
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(
                        robots_url,
                        timeout=aiohttp.ClientTimeout(total=10),
                        headers={"User-Agent": USER_AGENTS[0]},
                    ) as response:
                        if response.status == 200:
                            content = await response.text()
                            parser = RobotFileParser()
                            parser.parse(content.splitlines())
                            self._parsers[domain] = parser
                            self._cache_timestamps[domain] = now

                            # Log crawl-delay if present
                            delay = parser.crawl_delay("*")
                            if delay:
                                logger.info(
                                    "robots_crawl_delay_found",
                                    domain=domain,
                                    delay=delay,
                                )

                            return parser
                        else:
                            # No robots.txt or error → allow all
                            logger.debug(
                                "robots_txt_not_found",
                                domain=domain,
                                status=response.status,
                            )
                            return None

            except Exception as e:
                logger.warning(
                    "robots_txt_fetch_failed",
                    domain=domain,
                    error=str(e),
                )
                return None

    def clear_cache(self) -> None:
        """Clear all cached robots.txt parsers."""
        self._parsers.clear()
        self._crawl_delays.clear()
        self._cache_timestamps.clear()


# Module-level singleton
_robots_checker: RobotsChecker | None = None


def get_robots_checker() -> RobotsChecker:
    """Get the global robots.txt checker singleton."""
    global _robots_checker  # noqa: PLW0603
    if _robots_checker is None:
        _robots_checker = RobotsChecker()
    return _robots_checker
