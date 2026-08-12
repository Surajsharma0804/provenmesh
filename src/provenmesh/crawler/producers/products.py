"""Product vertical producer — discovers AI product/tool pages."""

from __future__ import annotations

from provenmesh.crawler.fetcher import TieredFetcher
from provenmesh.crawler.producers.base import BaseProducer
from provenmesh.observability.logging import get_logger

logger = get_logger(__name__)


class ProductProducer(BaseProducer):
    """Discovers AI product listing pages and enqueues detail URLs.

    Sources: Product Hunt AI category, Futurepedia, AI tool directories.
    """

    @property
    def vertical_name(self) -> str:
        return "products"

    @property
    def record_type(self) -> str:
        return "PRODUCT"

    async def discover_urls(self) -> None:
        fetcher = TieredFetcher()
        checkpoint = await self._load_checkpoint("products")
        start_page = checkpoint.get("page", 0) + 1

        # Futurepedia AI tools directory
        for page in range(start_page, 101):
            listing_url = f"https://www.futurepedia.io/ai-tools?page={page}"
            result = await fetcher.fetch(
                listing_url,
                source_name="futurepedia",
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
                    source_name="futurepedia",
                    listing_page=page,
                    fetch_tier=1,
                )

            await self._save_checkpoint("products", page, listing_url)

    def _extract_detail_urls(self, html: str, base_url: str) -> list[str]:
        """Extract product detail page URLs from a listing page."""
        from bs4 import BeautifulSoup

        from provenmesh.crawler.normalization import normalize_url

        soup = BeautifulSoup(html, "lxml")
        urls: list[str] = []

        # Futurepedia tool cards
        for link in soup.select("a.tool-card, a[href*='/tool/']"):
            href = link.get("href", "")
            if href:
                full_url = normalize_url(str(href), base_url)
                if full_url:
                    urls.append(full_url)

        # Product Hunt posts
        for link in soup.select("a[data-test='post-name'], a[href*='/posts/']"):
            href = link.get("href", "")
            if href:
                full_url = normalize_url(str(href), base_url)
                if full_url:
                    urls.append(full_url)

        return urls
