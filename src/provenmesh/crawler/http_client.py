"""HTTP client — Tier 1 fetching via aiohttp (PDF §7.1).

aiohttp is the cheapest fetch method — 8-10x cheaper per request than
spinning up a Playwright browser context (PDF §3.1). Used for the
majority of sources.

Connection pooling configured per hardening suggestion §7:
    - Total pool size: 100
    - Per-host limit: 5
    - DNS cache TTL: 300s
    - Keepalive: 30s
"""

from __future__ import annotations

import random
import time

import aiohttp

from provenmesh.config.constants import USER_AGENTS
from provenmesh.config.settings import get_settings
from provenmesh.observability.logging import get_logger
from provenmesh.observability.metrics import (
    FETCH_LATENCY,
    HTTP_5XX_TOTAL,
    HTTP_429_TOTAL,
)

logger = get_logger(__name__)

_session: aiohttp.ClientSession | None = None


class FetchResult:
    """Result of an HTTP fetch operation."""

    __slots__ = (
        "content",
        "content_type",
        "elapsed_ms",
        "encoding",
        "error",
        "fetch_tier",
        "headers",
        "status",
        "url",
    )

    def __init__(
        self,
        url: str,
        status: int = 0,
        content: bytes = b"",
        content_type: str = "",
        encoding: str = "utf-8",
        headers: dict[str, str] | None = None,
        elapsed_ms: float = 0,
        fetch_tier: int = 1,
        error: str = "",
    ) -> None:
        self.url = url
        self.status = status
        self.content = content
        self.content_type = content_type
        self.encoding = encoding
        self.headers = headers or {}
        self.elapsed_ms = elapsed_ms
        self.fetch_tier = fetch_tier
        self.error = error

    @property
    def ok(self) -> bool:
        return 200 <= self.status < 400 and not self.error

    @property
    def text(self) -> str:
        """Decode content with detected encoding (hardening §11)."""
        try:
            return self.content.decode(self.encoding)
        except (UnicodeDecodeError, LookupError):
            try:
                return self.content.decode("utf-8", errors="replace")
            except Exception:
                return self.content.decode("latin-1", errors="replace")

    @property
    def is_rate_limited(self) -> bool:
        return self.status == 429

    @property
    def is_server_error(self) -> bool:
        return 500 <= self.status < 600


async def get_http_session() -> aiohttp.ClientSession:
    """Get or create a shared aiohttp session with connection pooling.

    Connection pooling configured per hardening suggestion §7.
    """
    global _session
    if _session is None or _session.closed:
        settings = get_settings()
        connector = aiohttp.TCPConnector(
            limit=100,
            limit_per_host=settings.max_domain_concurrency,
            ttl_dns_cache=300,
            keepalive_timeout=30,
            enable_cleanup_closed=True,
            force_close=False,
        )
        _session = aiohttp.ClientSession(
            connector=connector,
            timeout=aiohttp.ClientTimeout(total=settings.fetch_timeout_seconds),
        )
    return _session


async def close_http_session() -> None:
    """Close the shared HTTP session."""
    global _session
    if _session and not _session.closed:
        await _session.close()
        _session = None


async def fetch_url(
    url: str,
    *,
    headers: dict[str, str] | None = None,
    follow_redirects: bool = True,
    timeout: int | None = None,
) -> FetchResult:
    """Fetch a URL via aiohttp (Tier 1).

    Uses rotating realistic User-Agent headers to avoid trivial
    bot fingerprinting.
    """
    session = await get_http_session()
    settings = get_settings()

    # Rotating User-Agent (PDF §7.1)
    request_headers: dict[str, str] = {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "DNT": "1",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
    }
    if headers:
        request_headers.update(headers)

    start = time.monotonic()
    try:
        async with session.get(
            url,
            headers=request_headers,
            allow_redirects=follow_redirects,
            timeout=aiohttp.ClientTimeout(total=timeout or settings.fetch_timeout_seconds),
        ) as response:
            content = await response.read()
            elapsed = (time.monotonic() - start) * 1000

            # Detect encoding (hardening §11)
            encoding = response.charset or "utf-8"
            content_type = response.content_type or ""

            # Track metrics
            FETCH_LATENCY.labels(fetch_tier="1").observe(elapsed / 1000)
            if response.status == 429:
                HTTP_429_TOTAL.labels(source=url).inc()
            elif response.status >= 500:
                HTTP_5XX_TOTAL.labels(source=url).inc()

            result_headers = {k: v for k, v in response.headers.items()}

            return FetchResult(
                url=str(response.url),
                status=response.status,
                content=content,
                content_type=content_type,
                encoding=encoding,
                headers=result_headers,
                elapsed_ms=elapsed,
                fetch_tier=1,
            )

    except aiohttp.ClientError as e:
        elapsed = (time.monotonic() - start) * 1000
        logger.warning("http_fetch_failed", url=url, error=str(e), elapsed_ms=elapsed)
        return FetchResult(url=url, error=str(e), elapsed_ms=elapsed, fetch_tier=1)
    except TimeoutError:
        elapsed = (time.monotonic() - start) * 1000
        logger.warning("http_fetch_timeout", url=url, elapsed_ms=elapsed)
        return FetchResult(url=url, error="timeout", elapsed_ms=elapsed, fetch_tier=1)


