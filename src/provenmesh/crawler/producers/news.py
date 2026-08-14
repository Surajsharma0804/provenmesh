"""News vertical producer -- discovers AI news articles."""

from __future__ import annotations

import asyncio
import xml.etree.ElementTree as ET

import aiohttp

from provenmesh.crawler.producers.base import BaseProducer
from provenmesh.observability.logging import get_logger

logger = get_logger(__name__)

_API_HEADERS = {
    "User-Agent": "ProvenMesh/1.0 RSS Reader",
    "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml, */*",
}

# Reliable RSS feeds -- no robots.txt issues, no brotli issues
_RSS_FEEDS = [
    ("https://techcrunch.com/category/artificial-intelligence/feed/", "techcrunch_ai"),
    ("https://feeds.feedburner.com/venturebeat/SZYF", "venturebeat_ai"),
    ("https://www.theverge.com/rss/index.xml", "theverge_ai"),
    ("https://rss.arxiv.org/rss/cs.AI", "arxiv_news"),
    ("https://aiweekly.co/issues.rss", "aiweekly"),
]


class NewsProducer(BaseProducer):
    """Discovers AI news articles via RSS feeds.

    Uses RSS feeds directly -- no robots.txt issues, no brotli compression.
    """

    @property
    def vertical_name(self) -> str:
        return "news"

    @property
    def record_type(self) -> str:
        return "NEWS_SIGNAL"

    async def discover_urls(self) -> None:
        discovered = 0
        timeout = aiohttp.ClientTimeout(total=20)

        async with aiohttp.ClientSession(timeout=timeout, headers=_API_HEADERS) as session:
            for feed_url, source_name in _RSS_FEEDS:
                try:
                    async with session.get(feed_url) as response:
                        if response.status == 200:
                            xml_text = await response.text()
                            urls = self._parse_rss_feed(xml_text, feed_url)
                            for url in urls:
                                await self._enqueue_url(url, source_name=source_name, listing_page=0, fetch_tier=1)
                                discovered += 1
                            logger.info("rss_feed_done", feed=feed_url, count=len(urls))
                        else:
                            logger.warning("rss_feed_failed", feed=feed_url, status=response.status)
                except Exception as e:
                    logger.warning("rss_feed_error", feed=feed_url, error=str(e))
                await asyncio.sleep(1)

        await self._save_checkpoint("news", 1, "done")
        logger.info("news_producer_done", urls_discovered=discovered)

    def _parse_rss_feed(self, xml_text: str, feed_url: str) -> list[str]:
        """Parse RSS/Atom feed and extract article URLs."""
        urls: list[str] = []
        try:
            root = ET.fromstring(xml_text)  # noqa: S314

            # RSS 2.0
            for item in root.findall(".//item"):
                link = item.find("link")
                if link is not None and link.text:
                    urls.append(link.text.strip())
                else:
                    # Some RSS use <guid> as URL
                    guid = item.find("guid")
                    if guid is not None and guid.text and guid.text.startswith("http"):
                        urls.append(guid.text.strip())

            # Atom feeds
            ns = {"atom": "http://www.w3.org/2005/Atom"}
            for entry in root.findall("atom:entry", ns):
                for link in entry.findall("atom:link", ns):
                    href = link.get("href", "")
                    rel = link.get("rel", "alternate")
                    if href and rel == "alternate":
                        urls.append(href)
                        break

        except ET.ParseError as e:
            logger.error("rss_parse_error", feed=feed_url, error=str(e))

        # Deduplicate while preserving order
        seen: set[str] = set()
        unique: list[str] = []
        for url in urls:
            if url not in seen and url.startswith("http"):
                seen.add(url)
                unique.append(url)

        return unique[:200]
