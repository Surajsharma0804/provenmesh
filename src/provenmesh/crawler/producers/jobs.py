"""Jobs vertical producer -- discovers AI job listings."""

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
    "Accept-Encoding": "gzip, deflate",
}

# Reliable public job board sources
_SOURCES = [
    ("https://remoteok.com/remote-ai-jobs", "remoteok"),
    ("https://remoteok.com/remote-machine-learning-jobs", "remoteok"),
    ("https://jobs.lever.co/openai", "openai_jobs"),
    ("https://jobs.lever.co/anthropic", "anthropic_jobs"),
    ("https://careers.google.com/jobs/results/?q=machine+learning", "google_careers"),
    ("https://www.linkedin.com/jobs/search/?keywords=AI+engineer&location=United+States&f_WT=2", "linkedin"),
]


class JobsProducer(BaseProducer):
    """Discovers AI job listing pages from reliable public sources."""

    @property
    def vertical_name(self) -> str:
        return "jobs"

    @property
    def record_type(self) -> str:
        return "JOB"

    async def discover_urls(self) -> None:
        discovered = 0
        timeout = aiohttp.ClientTimeout(total=30)

        async with aiohttp.ClientSession(timeout=timeout, headers=_API_HEADERS) as session:
            for source_url, source_name in _SOURCES:
                try:
                    async with session.get(source_url) as response:
                        if response.status == 200:
                            html = await response.text()
                            urls = self._extract_job_urls(html, source_url, source_name)
                            for url in urls:
                                await self._enqueue_url(url, source_name=source_name, listing_page=0, fetch_tier=1)
                                discovered += 1
                            logger.info("jobs_source_done", source=source_url, count=len(urls))
                        else:
                            logger.warning("jobs_source_failed", url=source_url, status=response.status)
                except Exception as e:
                    logger.warning("jobs_fetch_error", url=source_url, error=str(e))
                await asyncio.sleep(2)

        await self._save_checkpoint("jobs", 1, "done")
        logger.info("jobs_producer_done", urls_discovered=discovered)

    def _extract_job_urls(self, html: str, base_url: str, source_name: str) -> list[str]:
        """Extract job listing URLs from various job board pages."""
        soup = BeautifulSoup(html, "lxml")
        urls: list[str] = []

        # RemoteOK job cards
        for link in soup.select("a[href*='/remote-jobs/'], a[data-href*='/remote-jobs/']"):
            href = str(link.get("href", "") or link.get("data-href", ""))
            if href:
                full_url = normalize_url(href, "https://remoteok.com")
                if full_url and full_url not in urls:
                    urls.append(full_url)

        # Lever.co job links
        if "lever.co" in base_url:
            for link in soup.select("a.posting-title, a[href*='/lever.co/']"):
                href = str(link.get("href", ""))
                if href and full_url not in urls:
                    urls.append(href)

        # Generic job listing links
        for link in soup.select("a[href*='/job/'], a[href*='/jobs/'], a[href*='/career']"):
            href = str(link.get("href", ""))
            if href:
                full_url = normalize_url(href, base_url)
                if full_url and full_url not in urls:
                    urls.append(full_url)

        return urls[:100]
