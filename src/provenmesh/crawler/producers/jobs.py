"""Jobs vertical producer — discovers AI job listings."""

from __future__ import annotations

from provenmesh.crawler.fetcher import TieredFetcher
from provenmesh.crawler.producers.base import BaseProducer
from provenmesh.observability.logging import get_logger

logger = get_logger(__name__)


class JobsProducer(BaseProducer):
    """Discovers AI job listing pages and enqueues detail URLs.

    Sources: AI job boards, company career pages.
    """

    @property
    def vertical_name(self) -> str:
        return "jobs"

    @property
    def record_type(self) -> str:
        return "JOB"

    async def discover_urls(self) -> None:
        fetcher = TieredFetcher()
        checkpoint = await self._load_checkpoint("jobs")
        start_page = checkpoint.get("page", 0) + 1

        # AI Jobs Net
        for page in range(start_page, 51):
            listing_url = f"https://aijobs.net/?page={page}"
            result = await fetcher.fetch(
                listing_url,
                source_name="ai_jobs_net",
                record_type=self.record_type,
                max_tier=1,
            )
            if not result.ok:
                break

            urls = self._extract_detail_urls(result.text, listing_url)
            if not urls:
                break

            for url in urls:
                await self._enqueue_url(
                    url,
                    source_name="ai_jobs_net",
                    listing_page=page,
                    fetch_tier=1,
                )

            await self._save_checkpoint("jobs", page, listing_url)

    def _extract_detail_urls(self, html: str, base_url: str) -> list[str]:
        """Extract job detail URLs from listing HTML."""
        from bs4 import BeautifulSoup

        from provenmesh.crawler.normalization import normalize_url

        soup = BeautifulSoup(html, "lxml")
        urls: list[str] = []

        for link in soup.select("a.job-listing, a[href*='/job/'], a[href*='/jobs/']"):
            href = link.get("href", "")
            if href:
                full_url = normalize_url(str(href), base_url)
                if full_url:
                    urls.append(full_url)

        return urls
