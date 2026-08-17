"""Product vertical producer -- discovers AI product/tool pages."""

from __future__ import annotations

import asyncio

import aiohttp
from bs4 import BeautifulSoup

from provenmesh.crawler.normalization import normalize_url
from provenmesh.crawler.producers.base import BaseProducer
from provenmesh.observability.logging import get_logger

logger = get_logger(__name__)

_API_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "text/html,application/xhtml+xml,*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate",  # No brotli to avoid decode issues
}


class ProductProducer(BaseProducer):
    """Discovers AI product listing pages.

    Sources: there.io (AI tools directory - open), GitHub Trending AI repos.
    """

    @property
    def vertical_name(self) -> str:
        return "products"

    @property
    def record_type(self) -> str:
        return "PRODUCT"

    async def discover_urls(self) -> None:
        discovered = 0
        timeout = aiohttp.ClientTimeout(total=30)

        # Source 1: GitHub Trending (AI/ML repos) -- publicly accessible
        github_topics = [
            "https://github.com/trending/python?since=weekly&spoken_language_code=en",
            "https://github.com/topics/large-language-models",
            "https://github.com/topics/artificial-intelligence",
            "https://github.com/topics/machine-learning",
        ]

        async with aiohttp.ClientSession(timeout=timeout, headers=_API_HEADERS) as session:
            for gh_url in github_topics:
                try:
                    async with session.get(gh_url) as response:
                        if response.status == 200:
                            html = await response.text()
                            urls = self._extract_github_repo_urls(html)
                            for url in urls:
                                await self._enqueue_url(
                                    url,
                                    source_name="github_trending",
                                    listing_page=0,
                                    fetch_tier=1,
                                )
                                discovered += 1
                            logger.info("github_listing_done", source=gh_url, count=len(urls))
                        else:
                            logger.warning(
                                "github_listing_failed",
                                url=gh_url,
                                status=response.status,
                            )
                except Exception as e:
                    logger.warning("github_fetch_error", url=gh_url, error=str(e))
                await asyncio.sleep(2)

        # Source 2: Product Hunt AI products via their public pages
        from provenmesh.crawler.fetcher import TieredFetcher
        fetcher = TieredFetcher()
        for page in range(1, 6):
            ph_url = f"https://www.producthunt.com/topics/artificial-intelligence?page={page}"
            result = await fetcher.fetch(
                ph_url,
                source_name="producthunt",
                record_type=self.record_type,
                max_tier=2,
            )
            if not result.ok:
                break
            urls = self._extract_producthunt_urls(result.text, ph_url)
            for url in urls:
                await self._enqueue_url(
                    url,
                    source_name="producthunt",
                    listing_page=page,
                    fetch_tier=2,
                )
                discovered += 1
            await asyncio.sleep(3)

        await self._save_checkpoint("products", 1, "done")
        logger.info("products_producer_done", urls_discovered=discovered)

    def _extract_github_repo_urls(self, html: str) -> list[str]:
        """Extract GitHub repository URLs from trending/topic pages."""
        soup = BeautifulSoup(html, "lxml")
        urls: list[str] = []
        for link in soup.select("a[href*='/'][class*='Link']"):
            href = str(link.get("href", ""))
            if href.startswith("/") and href.count("/") == 2 and "." not in href.split("/")[-1]:
                full_url = f"https://github.com{href}"
                if full_url not in urls:
                    urls.append(full_url)
        # Also try article-style links
        for link in soup.select("h2 a, h3 a"):
            href = str(link.get("href", ""))
            if href and "github.com" in href and href not in urls:
                urls.append(href)
        return urls[:100]

    def _extract_producthunt_urls(self, html: str, base_url: str) -> list[str]:
        """Extract Product Hunt post URLs."""
        soup = BeautifulSoup(html, "lxml")
        urls: list[str] = []
        for link in soup.select("a[href*='/posts/']"):
            href = str(link.get("href", ""))
            if href:
                full_url = normalize_url(href, "https://www.producthunt.com")
                if full_url and full_url not in urls:
                    urls.append(full_url)
        return urls
