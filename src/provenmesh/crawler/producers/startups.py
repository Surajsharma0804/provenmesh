"""Startup vertical producer -- discovers AI startup company pages."""

from __future__ import annotations

import asyncio

import aiohttp
from bs4 import BeautifulSoup

from provenmesh.crawler.normalization import normalize_url
from provenmesh.crawler.producers.base import BaseProducer
from provenmesh.observability.logging import get_logger

logger = get_logger(__name__)

_API_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,*/*",
    "Accept-Language": "en-US,en;q=0.9",
}

# YC public JSON API — returns actual company data without JS rendering
_YC_API_URLS = [
    "https://api.ycombinator.com/v0.1/companies?batch=W24&tags=AI",
    "https://api.ycombinator.com/v0.1/companies?batch=S24&tags=AI",
    "https://api.ycombinator.com/v0.1/companies?batch=W25&tags=AI",
    "https://api.ycombinator.com/v0.1/companies?industry=B2B&tags=AI",
]


class StartupProducer(BaseProducer):
    """Discovers AI startup listing pages and enqueues detail URLs.

    Uses YC company directory (publicly accessible JSON API) and
    TechCrunch article pages as reliable startup sources.
    """

    @property
    def vertical_name(self) -> str:
        return "startups"

    @property
    def record_type(self) -> str:
        return "STARTUP"

    async def discover_urls(self) -> None:
        discovered = 0
        timeout = aiohttp.ClientTimeout(total=30)

        # Source 1: YC public JSON API
        async with aiohttp.ClientSession(timeout=timeout, headers=_API_HEADERS) as session:
            for yc_url in _YC_API_URLS:
                try:
                    async with session.get(yc_url) as response:
                        if response.status == 200:
                            try:
                                data = await response.json()
                                companies = data.get("companies", []) if isinstance(data, dict) else []
                                for company in companies:
                                    website = company.get("website", "")
                                    if website and website.startswith("http"):
                                        await self._enqueue_url(website, source_name="ycombinator", listing_page=0, fetch_tier=1)
                                        discovered += 1
                                logger.info("yc_api_done", source=yc_url, count=len(companies))
                            except Exception:
                                # Fallback: try HTML parsing
                                html = await response.text()
                                urls = self._extract_yc_company_urls(html, yc_url)
                                for url in urls:
                                    await self._enqueue_url(url, source_name="ycombinator", listing_page=0, fetch_tier=1)
                                    discovered += 1
                                logger.info("yc_html_done", source=yc_url, count=len(urls))
                        else:
                            logger.warning("yc_api_failed", url=yc_url, status=response.status)
                except Exception as e:
                    logger.warning("yc_fetch_error", url=yc_url, error=str(e))
                await asyncio.sleep(2)

        # Source 2: TechCrunch AI category pages
        from provenmesh.crawler.fetcher import TieredFetcher
        fetcher = TieredFetcher()
        for page in range(1, 11):
            tc_url = f"https://techcrunch.com/category/artificial-intelligence/page/{page}/"
            result = await fetcher.fetch(tc_url, source_name="techcrunch_ai", record_type=self.record_type, max_tier=1)
            if not result.ok:
                break
            urls = self._extract_techcrunch_urls(result.text, tc_url)
            for url in urls:
                await self._enqueue_url(url, source_name="techcrunch_ai", listing_page=page, fetch_tier=1)
                discovered += 1
            await asyncio.sleep(2)

        await self._save_checkpoint("startups", 1, "done")
        logger.info("startups_producer_done", urls_discovered=discovered)

    def _extract_yc_company_urls(self, html: str, base_url: str) -> list[str]:
        """Extract YC company profile URLs."""
        soup = BeautifulSoup(html, "lxml")
        urls: list[str] = []
        for link in soup.select("a[href*='/companies/']"):
            href = link.get("href", "")
            if href and "/companies/" in str(href) and "?" not in str(href):
                full_url = normalize_url(str(href), "https://www.ycombinator.com")
                if full_url and full_url not in urls:
                    urls.append(full_url)
        return urls[:200]

    def _extract_techcrunch_urls(self, html: str, base_url: str) -> list[str]:
        """Extract TechCrunch article URLs."""
        soup = BeautifulSoup(html, "lxml")
        urls: list[str] = []
        for link in soup.select("a.post-block__title__link, h2 a, h3 a"):
            href = link.get("href", "")
            if href and "techcrunch.com" in str(href):
                full_url = normalize_url(str(href), base_url)
                if full_url and full_url not in urls:
                    urls.append(full_url)
        return urls
