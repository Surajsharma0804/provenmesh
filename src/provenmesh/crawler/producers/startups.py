"""Startup vertical producer -- discovers ALL AI startup company pages.

Sources (all public, no auth required):
    1. YC Company Directory - all batches with AI tag (W19-W25, S19-S24)
    2. Google AI demo companies — public pages
    3. Crunchbase trending — public search API
    4. TechCrunch AI articles — RSS feed (reliable, no JS)
    5. Sifted EU startups — RSS
    6. Product Hunt AI launches — public JSON API
    7. AngelList / Wellfound — public company search
    8. AI startup databases — futurepedia, theresanaiforthat
"""

from __future__ import annotations

import asyncio

import aiohttp
import feedparser
from bs4 import BeautifulSoup

from provenmesh.crawler.normalization import normalize_url
from provenmesh.crawler.producers.base import BaseProducer
from provenmesh.observability.logging import get_logger

logger = get_logger(__name__)

_API_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,*/*",
    "Accept-Language": "en-US,en;q=0.9",
}

# ─── YC API: all recent batches with AI tag ────────────────────────────────
# Each request returns up to 20 companies — we cover all major batches
_YC_API_URLS = [
    # 2025 batches
    "https://api.ycombinator.com/v0.1/companies?batch=W25&tags=AI",
    "https://api.ycombinator.com/v0.1/companies?batch=S24&tags=AI",
    "https://api.ycombinator.com/v0.1/companies?batch=W24&tags=AI",
    "https://api.ycombinator.com/v0.1/companies?batch=S23&tags=AI",
    "https://api.ycombinator.com/v0.1/companies?batch=W23&tags=AI",
    "https://api.ycombinator.com/v0.1/companies?batch=S22&tags=AI",
    "https://api.ycombinator.com/v0.1/companies?batch=W22&tags=AI",
    "https://api.ycombinator.com/v0.1/companies?batch=S21&tags=AI",
    "https://api.ycombinator.com/v0.1/companies?batch=W21&tags=AI",
    "https://api.ycombinator.com/v0.1/companies?batch=S20&tags=AI",
    "https://api.ycombinator.com/v0.1/companies?batch=W20&tags=AI",
    "https://api.ycombinator.com/v0.1/companies?batch=S19&tags=AI",
    "https://api.ycombinator.com/v0.1/companies?batch=W19&tags=AI",
    # By industry/tag for broader coverage
    "https://api.ycombinator.com/v0.1/companies?industry=B2B&tags=AI",
    "https://api.ycombinator.com/v0.1/companies?industry=Healthcare&tags=AI",
    "https://api.ycombinator.com/v0.1/companies?industry=Education&tags=AI",
    "https://api.ycombinator.com/v0.1/companies?industry=Consumer&tags=AI",
    "https://api.ycombinator.com/v0.1/companies?tags=Generative+AI",
    "https://api.ycombinator.com/v0.1/companies?tags=Machine+Learning",
    "https://api.ycombinator.com/v0.1/companies?tags=LLM",
    "https://api.ycombinator.com/v0.1/companies?tags=NLP",
    "https://api.ycombinator.com/v0.1/companies?tags=Computer+Vision",
    "https://api.ycombinator.com/v0.1/companies?tags=Robotics",
]

# ─── RSS feeds: reliable, no JS, high quality AI startup coverage ──────────
_RSS_SOURCES = [
    ("https://techcrunch.com/feed/", "techcrunch"),
    ("https://feeds.feedburner.com/venturebeat/SZYF", "venturebeat"),
    ("https://sifted.eu/feed", "sifted"),
    ("https://www.eu-startups.com/feed/", "eu_startups"),
    ("https://feeds.arstechnica.com/arstechnica/index", "arstechnica"),
    ("https://www.theinformation.com/feed", "theinformation"),
]

# ─── Direct known AI startup company pages ────────────────────────────────
# These are flagship AI startups — each a detail page we directly enqueue
_KNOWN_AI_STARTUPS = [
    "https://openai.com", "https://anthropic.com", "https://cohere.com",
    "https://mistral.ai", "https://deepmind.google", "https://inflection.ai",
    "https://adept.ai", "https://stability.ai", "https://huggingface.co",
    "https://replicate.com", "https://runway.ml", "https://pika.art",
    "https://midjourney.com", "https://elevenlabs.io", "https://otter.ai",
    "https://jasper.ai", "https://copy.ai", "https://notion.so",
    "https://grammarly.com", "https://character.ai", "https://perplexity.ai",
    "https://you.com", "https://together.ai", "https://scale.com",
    "https://labelbox.com", "https://datarobot.com", "https://c3.ai",
    "https://h2o.ai", "https://databricks.com", "https://anyscale.com",
    "https://modal.com", "https://banana.dev", "https://baseten.co",
    "https://lightning.ai", "https://wandb.ai", "https://comet.ml",
    "https://deepgram.com", "https://assembly.ai", "https://rev.com",
    "https://descript.com", "https://synthesis.ai", "https://d-id.com",
    "https://heygen.com", "https://colossyan.com", "https://synthesia.io",
    "https://luma.ai", "https://krea.ai", "https://ideogram.ai",
    "https://adobe.com/ai", "https://canva.com", "https://gamma.app",
    "https://beautiful.ai", "https://tome.app", "https://pitch.com",
    "https://miro.com", "https://figjam.com", "https://whimsical.com",
    "https://linear.app", "https://height.app", "https://clickup.com",
    "https://cursor.so", "https://replit.com", "https://github.com/features/copilot",
    "https://tabnine.com", "https://codeium.com", "https://sourcegraph.com",
    "https://weaviate.io", "https://pinecone.io", "https://milvus.io",
    "https://chroma.run", "https://qdrant.tech", "https://vespa.ai",
    "https://langchain.com", "https://llamaindex.ai", "https://guardrailsai.com",
    "https://trulens.org", "https://humanloop.com", "https://brainlid.org",
    "https://cohere.com", "https://ai21.com", "https://alephalpha.com",
    "https://writer.com", "https://typeface.ai", "https://lately.ai",
    "https://phrasee.co", "https://persado.com", "https://anyword.com",
    "https://moveworks.com", "https://aisera.com", "https://kore.ai",
    "https://cognigy.com", "https://yellow.ai", "https://intercom.com",
    "https://drift.com", "https://qualified.com", "https://insider.com",
]


class StartupProducer(BaseProducer):
    """Discovers ALL AI startup company pages from multiple sources.

    Sources: YC API (all batches), RSS feeds, known AI startups,
    TechCrunch AI category pages.
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

        # ── Source 1: YC company API (all batches) ─────────────────────
        async with aiohttp.ClientSession(
            timeout=timeout, headers=_API_HEADERS,
        ) as session:
            for yc_url in _YC_API_URLS:
                try:
                    async with session.get(yc_url) as response:
                        if response.status == 200:
                            try:
                                data = await response.json()
                                companies = (
                                    data.get("companies", [])
                                    if isinstance(data, dict) else []
                                )
                                for company in companies:
                                    # Enqueue company website for detail extraction
                                    website = company.get("website", "")
                                    if website and website.startswith("http"):
                                        await self._enqueue_url(
                                            website,
                                            source_name="ycombinator",
                                            listing_page=0,
                                            fetch_tier=1,
                                        )
                                        discovered += 1
                                    # Also enqueue YC profile page
                                    slug = company.get("slug", "")
                                    if slug:
                                        yc_profile = f"https://www.ycombinator.com/companies/{slug}"
                                        await self._enqueue_url(
                                            yc_profile,
                                            source_name="ycombinator",
                                            listing_page=0,
                                            fetch_tier=1,
                                        )
                                        discovered += 1
                                logger.info(
                                    "yc_api_done",
                                    source=yc_url,
                                    count=len(companies),
                                )
                            except Exception as parse_err:
                                # JSON parse failure — log and skip,
                                # the outer HTML fallback is not needed here
                                logger.debug(
                                    "yc_json_parse_skipped",
                                    url=yc_url,
                                    error=str(parse_err)[:80],
                                )
                        else:
                            logger.warning(
                                "yc_api_failed",
                                url=yc_url,
                                status=response.status,
                            )
                except Exception as e:
                    logger.warning("yc_fetch_error", url=yc_url, error=str(e))
                await asyncio.sleep(1)

        # ── Source 2: Known major AI startups (direct enqueue) ─────────
        for url in _KNOWN_AI_STARTUPS:
            await self._enqueue_url(
                url,
                source_name="known_ai_startups",
                listing_page=0,
                fetch_tier=1,
            )
            discovered += 1

        logger.info(
            "known_startups_enqueued", count=len(_KNOWN_AI_STARTUPS),
        )

        # ── Source 3: RSS feeds for startup articles ────────────────────
        async with aiohttp.ClientSession(
            timeout=timeout, headers=_API_HEADERS,
        ) as session:
            for rss_url, source_name in _RSS_SOURCES:
                try:
                    async with session.get(rss_url) as response:
                        if response.status == 200:
                            text = await response.text()
                            feed = feedparser.parse(text)
                            for entry in feed.entries[:50]:
                                link = entry.get("link", "")
                                title_body = (
                                    entry.get("title", "")
                                    + entry.get("summary", "")
                                ).lower()
                                _kws = ["startup", "ai ", "raises", "funding", "launch"]
                                if link and any(kw in title_body for kw in _kws):
                                    await self._enqueue_url(
                                        link,
                                        source_name=source_name,
                                        listing_page=0,
                                        fetch_tier=1,
                                    )
                                    discovered += 1
                            logger.info(
                                "rss_startup_feed_done",
                                source=source_name,
                                count=len(feed.entries),
                            )
                except Exception as e:
                    logger.warning(
                        "rss_startup_feed_error",
                        source=source_name,
                        error=str(e)[:80],
                    )
                await asyncio.sleep(1)

        # ── Source 4: TechCrunch AI pages ──────────────────────────────
        from provenmesh.crawler.fetcher import TieredFetcher
        fetcher = TieredFetcher()
        for page in range(1, 6):
            tc_url = (
                f"https://techcrunch.com/category/artificial-intelligence/page/{page}/"
            )
            result = await fetcher.fetch(
                tc_url,
                source_name="techcrunch_ai",
                record_type=self.record_type,
                max_tier=1,
            )
            if not result.ok:
                break
            urls = self._extract_techcrunch_urls(result.text, tc_url)
            for url in urls:
                await self._enqueue_url(
                    url,
                    source_name="techcrunch_ai",
                    listing_page=page,
                    fetch_tier=1,
                )
                discovered += 1
            await asyncio.sleep(2)

        await self._save_checkpoint("startups", 1, "done")
        logger.info("startups_producer_done", urls_discovered=discovered)

    def _extract_techcrunch_urls(self, html: str, base_url: str) -> list[str]:
        """Extract TechCrunch article URLs."""
        soup = BeautifulSoup(html, "lxml")
        urls: list[str] = []
        for link in soup.select(
            "a.post-block__title__link, h2 a, h3 a, a[data-event='article-click']",
        ):
            href = link.get("href", "")
            if href and "techcrunch.com" in str(href):
                full_url = normalize_url(str(href), base_url)
                if full_url and full_url not in urls:
                    urls.append(full_url)
        return urls
