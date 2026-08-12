"""News vertical producer — discovers AI news with freshness filtering."""

from __future__ import annotations

from provenmesh.crawler.fetcher import TieredFetcher
from provenmesh.crawler.producers.base import BaseProducer
from provenmesh.observability.logging import get_logger

logger = get_logger(__name__)


class NewsProducer(BaseProducer):
    """Discovers AI news articles from tech publications.

    News is treated as a signal, not a first-class entity (v2 §2).
    Freshness filtering ensures only recent articles are ingested.
    """

    @property
    def vertical_name(self) -> str:
        return "news"

    @property
    def record_type(self) -> str:
        return "NEWS_SIGNAL"

    async def discover_urls(self) -> None:
        fetcher = TieredFetcher()
        checkpoint = await self._load_checkpoint("news")
        start_page = checkpoint.get("page", 0) + 1

        # VentureBeat AI
        for page in range(start_page, 31):
            listing_url = f"https://venturebeat.com/category/ai/page/{page}/"
            result = await fetcher.fetch(
                listing_url,
                source_name="venturebeat_ai",
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
                    source_name="venturebeat_ai",
                    listing_page=page,
                    fetch_tier=1,
                )

            await self._save_checkpoint("news", page, listing_url)

    def _extract_detail_urls(self, html: str, base_url: str) -> list[str]:
        """Extract news article URLs from listing HTML."""
        from bs4 import BeautifulSoup

        from provenmesh.crawler.normalization import normalize_url

        soup = BeautifulSoup(html, "lxml")
        urls: list[str] = []

        # VentureBeat article links
        for link in soup.select(
            "a.article-title, a[class*='ArticleTitle'], "
            "h2 a, h3 a, a[href*='/2026/'], a[href*='/2025/']"
        ):
            href = link.get("href", "")
            if href and not href.startswith("#"):
                full_url = normalize_url(str(href), base_url)
                if full_url:
                    urls.append(full_url)

        return urls
