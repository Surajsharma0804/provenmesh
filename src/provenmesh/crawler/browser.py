"""Playwright browser — Tier 2 fetching (PDF §7.1).

Headless Chromium for JS-rendered content, with randomized viewport,
mouse-move, and scroll timing to avoid trivial bot fingerprints.

Browser context is recycled every N requests to prevent memory leaks
(hardening §8).
"""

from __future__ import annotations

import asyncio
import random
import time

from provenmesh.config.constants import PLAYWRIGHT_TIMEOUT, USER_AGENTS
from provenmesh.crawler.http_client import FetchResult
from provenmesh.observability.logging import get_logger
from provenmesh.observability.metrics import FETCH_LATENCY

logger = get_logger(__name__)

# Lazy import to avoid requiring Playwright when not used
_playwright = None
_browser = None
_context = None
_request_count = 0
_MAX_REQUESTS_PER_CONTEXT = 100  # Recycle after N requests (hardening §8)
_lock = asyncio.Lock()

# Random viewport sizes for fingerprint variation
_VIEWPORTS = [
    {"width": 1920, "height": 1080},
    {"width": 1366, "height": 768},
    {"width": 1536, "height": 864},
    {"width": 1440, "height": 900},
    {"width": 1280, "height": 720},
]


async def _ensure_browser() -> None:
    """Initialize Playwright browser if not already running."""
    global _playwright, _browser, _context, _request_count  # noqa: PLW0603
    async with _lock:
        if _browser is None or not _browser.is_connected():
            from playwright.async_api import async_playwright

            _playwright = await async_playwright().start()
            _browser = await _playwright.chromium.launch(
                headless=True,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-gpu",
                ],
            )
            _request_count = 0
            logger.info("playwright_browser_launched")

        # Recycle context after N requests (memory management)
        if _context is None or _request_count >= _MAX_REQUESTS_PER_CONTEXT:
            if _context:
                await _context.close()

            viewport = random.choice(_VIEWPORTS)
            _context = await _browser.new_context(
                viewport=viewport,
                user_agent=random.choice(USER_AGENTS),
                locale="en-US",
                timezone_id="America/New_York",
                java_script_enabled=True,
            )
            _request_count = 0
            logger.info(
                "playwright_context_recycled",
                viewport=f"{viewport['width']}x{viewport['height']}",
            )


async def fetch_with_browser(
    url: str,
    *,
    wait_for: str = "networkidle",
    timeout_ms: int = PLAYWRIGHT_TIMEOUT * 1000,
) -> FetchResult:
    """Fetch a URL using Playwright headless browser (Tier 2).

    Includes anti-bot measures:
    - Randomized viewport dimensions
    - Random mouse movements
    - Random scroll behavior
    - Realistic timing between actions
    """
    global _request_count  # noqa: PLW0603
    await _ensure_browser()

    start = time.monotonic()
    page = None

    try:
        page = await _context.new_page()  # type: ignore[union-attr]
        _request_count += 1

        # Navigate with realistic behavior
        response = await page.goto(url, wait_until=wait_for, timeout=timeout_ms)

        # Anti-bot: random mouse movement
        await page.mouse.move(
            random.randint(100, 800),
            random.randint(100, 600),
        )

        # Anti-bot: random scroll
        await page.evaluate(
            f"window.scrollTo(0, {random.randint(100, 500)})"
        )

        # Small realistic delay
        await asyncio.sleep(random.uniform(0.3, 1.0))

        # Get rendered content
        content = await page.content()
        elapsed = (time.monotonic() - start) * 1000

        status = response.status if response else 0
        headers = dict(response.headers) if response else {}

        FETCH_LATENCY.labels(fetch_tier="2").observe(elapsed / 1000)

        return FetchResult(
            url=url,
            status=status,
            content=content.encode("utf-8"),
            content_type="text/html",
            encoding="utf-8",
            headers=headers,
            elapsed_ms=elapsed,
            fetch_tier=2,
        )

    except Exception as e:
        elapsed = (time.monotonic() - start) * 1000
        logger.warning(
            "browser_fetch_failed",
            url=url,
            error=str(e),
            elapsed_ms=elapsed,
        )
        return FetchResult(
            url=url,
            error=str(e),
            elapsed_ms=elapsed,
            fetch_tier=2,
        )
    finally:
        if page:
            await page.close()


async def close_browser() -> None:
    """Clean up Playwright resources."""
    global _playwright, _browser, _context  # noqa: PLW0603
    if _context:
        await _context.close()
        _context = None
    if _browser:
        await _browser.close()
        _browser = None
    if _playwright:
        await _playwright.stop()
        _playwright = None
    logger.info("playwright_browser_closed")
