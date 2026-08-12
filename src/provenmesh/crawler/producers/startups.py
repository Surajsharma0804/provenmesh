"""Startup vertical producer — discovers AI startup company pages."""

from __future__ import annotations

from provenmesh.crawler.fetcher import TieredFetcher
from provenmesh.crawler.producers.base import BaseProducer
from provenmesh.observability.logging import get_logger

logger = get_logger(__name__)


class StartupProducer(BaseProducer):
    """Discovers AI startup listing pages and enqueues detail URLs.

    Sources: Crunchbase, TechCrunch, Y Combinator directories.
    """

    @property
    def vertical_name(self) -> str:
        return "startups"

    @property
    def record_type(self) -> str:
        return "STARTUP"

    async def discover_urls(self) -> None:
        fetcher = TieredFetcher()
        checkpoint = await self._load_checkpoint("startups")
        start_page = checkpoint.get("page", 0) + 1

        # Crunchbase AI organizations
        for page in range(start_page, 101):
            listing_url = (
                f"https://www.crunchbase.com/discover/organizations"
                f"?page={page}"
            )
            result = await fetcher.fetch(
                listing_url,
                source_name="crunchbase_listings",
                record_type=self.record_type,
                max_tier=2,
            )
            if not result.ok:
                logger.warning(
                    "listing_page_failed",
                    url=listing_url,
                    status=result.status,
                )
                break

            # Extract detail URLs from listing HTML
            urls = self._extract_detail_urls(result.text, listing_url)
            if not urls:
                logger.info("no_more_listings", page=page)
                break

            for url in urls:
                await self._enqueue_url(
                    url,
                    source_name="crunchbase_listings",
                    listing_page=page,
                    fetch_tier=2,
                )

            await self._save_checkpoint("startups", page, listing_url)

    def _extract_detail_urls(self, html: str, base_url: str) -> list[str]:
        """Extract company detail page URLs from a listing page."""
        from bs4 import BeautifulSoup

        from provenmesh.crawler.normalization import normalize_url

        soup = BeautifulSoup(html, "lxml")
        urls: list[str] = []

        # Crunchbase uses entity-link components
        for link in soup.select("a[href*='/organization/']"):
            href = link.get("href", "")
            if href and "/organization/" in str(href):
                full_url = normalize_url(str(href), base_url)
                if full_url:
                    urls.append(full_url)

        # TechCrunch article links
        for link in soup.select("a.loop-card__title-link, a[class*='post-block__title']"):
            href = link.get("href", "")
            if href:
                full_url = normalize_url(str(href), base_url)
                if full_url:
                    urls.append(full_url)

        # Y Combinator company cards
        for link in soup.select("a[href*='/companies/']"):
            href = link.get("href", "")
            if href and "/companies/" in str(href):
                full_url = normalize_url(str(href), base_url)
                if full_url:
                    urls.append(full_url)

        return urls
