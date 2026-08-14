"""News vertical producer -- discovers AI news articles from 20+ sources.

Sources:
- 20+ RSS feeds: TechCrunch, VentureBeat, ArXiv (AI/ML/NLP), The Verge,
  HuggingFace, DeepMind, OpenAI, Anthropic, Google AI, Microsoft AI,
  DeepLearning.AI, Import AI, Synced Review, Crunchbase News, and more.
- Hacker News API: live + historical backfill up to 30 days.

Every discovered URL is tagged with its source name so the Sheets export
always shows where each signal came from.
"""

from __future__ import annotations

import asyncio
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone

import aiohttp

from provenmesh.crawler.producers.base import BaseProducer
from provenmesh.observability.logging import get_logger

logger = get_logger(__name__)

_API_HEADERS = {
    "User-Agent": "ProvenMesh/1.0 (+https://github.com/Surajsharma0804/provenmesh)",
    "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml, */*",
}

# ─── 20+ RSS Feeds — every major AI news outlet ──────────────────────────────
_RSS_FEEDS = [
    # ── Primary tech/AI news ──────────────────────────────────────────────────
    ("https://techcrunch.com/category/artificial-intelligence/feed/", "techcrunch_ai"),
    ("https://feeds.feedburner.com/venturebeat/SZYF",                 "venturebeat_ai"),
    ("https://www.theverge.com/rss/index.xml",                        "theverge"),

    # ── ArXiv — AI / ML / NLP / CV ───────────────────────────────────────────
    ("https://rss.arxiv.org/rss/cs.AI",                               "arxiv_ai"),
    ("https://rss.arxiv.org/rss/cs.LG",                               "arxiv_ml"),
    ("https://rss.arxiv.org/rss/cs.CL",                               "arxiv_nlp"),
    ("https://rss.arxiv.org/rss/cs.CV",                               "arxiv_cv"),

    # ── Dedicated AI publications ─────────────────────────────────────────────
    ("https://www.artificialintelligence-news.com/feed/",             "ai_news"),
    ("https://syncedreview.com/feed/",                                 "synced_review"),
    ("https://aiweekly.co/issues.rss",                                 "aiweekly"),
    ("https://www.deeplearning.ai/the-batch/feed/",                    "deeplearning_batch"),
    ("https://import.ai/feed/",                                        "import_ai"),
    ("https://huggingface.co/blog/feed.xml",                          "huggingface_blog"),

    # ── Lab / company blogs ───────────────────────────────────────────────────
    ("https://deepmind.google/blog/rss.xml",                          "deepmind_blog"),
    ("https://openai.com/blog/rss.xml",                               "openai_blog"),
    ("https://www.anthropic.com/rss.xml",                             "anthropic_blog"),
    ("https://ai.googleblog.com/feeds/posts/default",                 "google_ai_blog"),
    ("https://blogs.microsoft.com/ai/feed/",                          "microsoft_ai"),
    ("https://stability.ai/news/rss.xml",                             "stability_ai"),

    # ── Business / funding ───────────────────────────────────────────────────
    ("https://news.ycombinator.com/rss",                              "hackernews"),
    ("https://feeds.feedburner.com/crunchbase-news",                  "crunchbase_news"),
    ("https://sifted.eu/feed/",                                        "sifted_eu"),

    # ── Wired + MIT Tech Review ───────────────────────────────────────────────
    ("https://www.wired.com/feed/category/artificial-intelligence/latest/rss", "wired_ai"),
    ("https://www.technologyreview.com/feed/",                        "mit_tech_review"),
]

# ── Hacker News search terms for AI story discovery ──────────────────────────
_HN_AI_TERMS = [
    "LLM", "GPT", "AI startup", "machine learning", "deep learning",
    "Anthropic", "OpenAI", "Gemini", "Claude", "artificial intelligence",
    "foundation model", "neural network", "transformer", "diffusion model",
]


class NewsProducer(BaseProducer):
    """Discovers AI news articles from 20+ RSS feeds + Hacker News API.

    - 20+ RSS feeds: TechCrunch, VentureBeat, ArXiv (AI/ML/NLP/CV),
      HuggingFace, DeepMind, OpenAI, Anthropic, Google AI, Microsoft AI,
      Wired, MIT Tech Review, Crunchbase News, and more.
    - Hacker News Algolia API: historical backfill up to 30 days back.
      Free, no API key required.
    """

    @property
    def vertical_name(self) -> str:
        return "news"

    @property
    def record_type(self) -> str:
        return "NEWS_SIGNAL"

    async def discover_urls(self) -> None:
        """Discover URLs from all RSS feeds in parallel + HN backfill."""
        timeout = aiohttp.ClientTimeout(total=25)
        async with aiohttp.ClientSession(timeout=timeout, headers=_API_HEADERS) as session:
            # Run all RSS feeds concurrently (much faster than sequential)
            rss_tasks = [
                self._fetch_rss(session, feed_url, source_name)
                for feed_url, source_name in _RSS_FEEDS
            ]
            results = await asyncio.gather(*rss_tasks, return_exceptions=True)
            rss_total = sum(r for r in results if isinstance(r, int))
            logger.info("all_rss_feeds_done", total_urls=rss_total, feeds=len(_RSS_FEEDS))

            # Historical backfill via Hacker News Algolia API (free, no key needed)
            hn_total = await self._backfill_hacker_news(session, days_back=30)
            logger.info("hn_backfill_done", urls=hn_total)

        await self._save_checkpoint("news", 1, "done")
        logger.info("news_producer_done", total_discovered=rss_total + hn_total)

    async def _fetch_rss(
        self, session: aiohttp.ClientSession, feed_url: str, source_name: str
    ) -> int:
        """Fetch a single RSS feed and enqueue all article URLs."""
        try:
            async with session.get(feed_url) as response:
                if response.status == 200:
                    xml_text = await response.text(errors="replace")
                    urls = self._parse_rss_feed(xml_text, feed_url)
                    for url in urls:
                        await self._enqueue_url(
                            url,
                            source_name=source_name,
                            listing_page=0,
                            fetch_tier=1,
                        )
                    logger.info("rss_feed_ok", source=source_name, count=len(urls))
                    return len(urls)
                else:
                    logger.warning("rss_feed_failed", source=source_name, status=response.status)
                    return 0
        except Exception as e:
            logger.warning("rss_feed_error", source=source_name, error=str(e)[:80])
            return 0

    async def _backfill_hacker_news(
        self, session: aiohttp.ClientSession, days_back: int = 30
    ) -> int:
        """Pull AI-related HN stories from the past N days via Algolia API.

        Uses https://hn.algolia.com/api — free, no key, returns full URL.
        Each story links directly to the original source article.
        """
        since_ts = int((datetime.now(timezone.utc) - timedelta(days=days_back)).timestamp())
        discovered = 0
        seen: set[str] = set()

        for term in _HN_AI_TERMS:
            try:
                url = (
                    f"https://hn.algolia.com/api/v1/search_by_date"
                    f"?query={term.replace(' ', '%20')}"
                    f"&tags=story"
                    f"&numericFilters=created_at_i>{since_ts}"
                    f"&hitsPerPage=50"
                )
                async with session.get(url, headers={"Accept": "application/json"}) as resp:
                    if resp.status != 200:
                        continue
                    data = await resp.json(content_type=None)
                    for hit in data.get("hits", []):
                        # Use the actual article URL, not the HN discussion page
                        article_url = hit.get("url") or ""
                        hn_url = f"https://news.ycombinator.com/item?id={hit.get('objectID','')}"
                        target = article_url if article_url.startswith("http") else hn_url
                        if target and target not in seen:
                            seen.add(target)
                            await self._enqueue_url(
                                target,
                                source_name="hackernews_ai",
                                listing_page=0,
                                fetch_tier=1,
                            )
                            discovered += 1
                await asyncio.sleep(0.5)   # be polite to Algolia
            except Exception as e:
                logger.warning("hn_backfill_error", term=term, error=str(e)[:80])

        return discovered

    def _parse_rss_feed(self, xml_text: str, feed_url: str) -> list[str]:
        """Parse RSS 2.0 and Atom feeds, return deduplicated article URLs."""
        urls: list[str] = []
        try:
            root = ET.fromstring(xml_text)  # noqa: S314

            # RSS 2.0
            for item in root.findall(".//item"):
                link = item.find("link")
                if link is not None and link.text:
                    urls.append(link.text.strip())
                else:
                    guid = item.find("guid")
                    if guid is not None and guid.text and guid.text.startswith("http"):
                        urls.append(guid.text.strip())

            # Atom
            ns = {"atom": "http://www.w3.org/2005/Atom"}
            for entry in root.findall("atom:entry", ns):
                for link in entry.findall("atom:link", ns):
                    href = link.get("href", "")
                    rel = link.get("rel", "alternate")
                    if href and rel == "alternate":
                        urls.append(href)
                        break

        except ET.ParseError as e:
            logger.warning("rss_parse_error", feed=feed_url, error=str(e)[:60])

        # Deduplicate, preserve order
        seen: set[str] = set()
        unique: list[str] = []
        for url in urls:
            if url not in seen and url.startswith("http"):
                seen.add(url)
                unique.append(url)

        return unique[:300]  # raised from 200 to 300 per feed

