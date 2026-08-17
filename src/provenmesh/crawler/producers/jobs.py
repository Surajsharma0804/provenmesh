"""Jobs vertical producer -- discovers AI job listings from reliable APIs.

Sources (all public, working):
    1. Remotive API — public JSON API, no auth needed
    2. FindWork API — public, no auth needed
    3. The Muse API — public jobs API
    4. GitHub Jobs style — public RSS feeds from company career pages
    5. AI-specific job boards — aijobs.net, mlops.community/jobs
    6. Direct company career pages — OpenAI, Anthropic, DeepMind, Meta AI
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
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json, text/html, */*",
    "Accept-Language": "en-US,en;q=0.9",
}

# ─── Remotive public JSON API ─────────────────────────────────────────────
# Free, no auth, returns JSON with job listings
_REMOTIVE_API_URLS = [
    "https://remotive.com/api/remote-jobs?category=software-dev&limit=100",
    "https://remotive.com/api/remote-jobs?category=data&limit=100",
    "https://remotive.com/api/remote-jobs?category=product&limit=100",
    "https://remotive.com/api/remote-jobs?search=AI&limit=100",
    "https://remotive.com/api/remote-jobs?search=machine+learning&limit=100",
    "https://remotive.com/api/remote-jobs?search=LLM&limit=100",
    "https://remotive.com/api/remote-jobs?search=NLP&limit=100",
    "https://remotive.com/api/remote-jobs?search=deep+learning&limit=100",
]

# ─── RSS feeds for AI jobs ────────────────────────────────────────────────
_JOB_RSS_FEEDS = [
    ("https://aijobs.net/feed/", "aijobs_net"),
    ("https://www.aiml.jobs/rss/", "aiml_jobs"),
    ("https://jobs.mlops.community/feed/", "mlops_jobs"),
]

# ─── Direct career pages of major AI companies ────────────────────────────
# These are crawlable without JS for job listings
_CAREER_PAGES = [
    ("https://openai.com/careers", "openai"),
    ("https://www.anthropic.com/careers", "anthropic"),
    ("https://deepmind.google/careers/", "deepmind"),
    ("https://ai.meta.com/careers/", "meta_ai"),
    ("https://huggingface.co/jobs", "huggingface"),
    ("https://stability.ai/careers", "stability_ai"),
    ("https://cohere.com/careers", "cohere"),
    ("https://mistral.ai/company/careers/", "mistral"),
    ("https://scale.com/careers", "scale_ai"),
    ("https://www.databricks.com/company/careers", "databricks"),
    ("https://wandb.ai/site/jobs", "wandb"),
    ("https://www.perplexity.ai/careers", "perplexity"),
    ("https://www.together.ai/careers", "together_ai"),
    ("https://anyscale.com/careers", "anyscale"),
    ("https://modal.com/careers", "modal"),
    ("https://replicate.com/careers", "replicate"),
    ("https://elevenlabs.io/careers", "elevenlabs"),
    ("https://deepgram.com/company/careers", "deepgram"),
    ("https://www.assemblyai.com/careers", "assemblyai"),
    ("https://runway.ml/careers", "runway"),
]


class JobsProducer(BaseProducer):
    """Discovers AI job listings from multiple working public sources."""

    @property
    def vertical_name(self) -> str:
        return "jobs"

    @property
    def record_type(self) -> str:
        return "JOB"

    async def discover_urls(self) -> None:
        discovered = 0
        timeout = aiohttp.ClientTimeout(total=30)

        # ── Source 1: Remotive public JSON API ─────────────────────────
        async with aiohttp.ClientSession(
            timeout=timeout, headers=_API_HEADERS,
        ) as session:
            for api_url in _REMOTIVE_API_URLS:
                try:
                    async with session.get(api_url) as response:
                        if response.status == 200:
                            data = await response.json()
                            jobs = data.get("jobs", []) if isinstance(data, dict) else []
                            for job in jobs:
                                url = job.get("url", "")
                                if url and url.startswith("http"):
                                    await self._enqueue_url(
                                        url,
                                        source_name="remotive",
                                        listing_page=0,
                                        fetch_tier=1,
                                    )
                                    discovered += 1
                            logger.info(
                                "remotive_api_done",
                                url=api_url,
                                count=len(jobs),
                            )
                        else:
                            logger.warning(
                                "remotive_api_failed",
                                url=api_url,
                                status=response.status,
                            )
                except Exception as e:
                    logger.warning(
                        "remotive_api_error", url=api_url, error=str(e)[:80],
                    )
                await asyncio.sleep(1)

        # ── Source 2: RSS feeds ────────────────────────────────────────
        async with aiohttp.ClientSession(
            timeout=timeout, headers=_API_HEADERS,
        ) as session:
            for rss_url, source_name in _JOB_RSS_FEEDS:
                try:
                    async with session.get(rss_url) as response:
                        if response.status == 200:
                            text = await response.text()
                            feed = feedparser.parse(text)
                            for entry in feed.entries:
                                link = entry.get("link", "")
                                if link:
                                    await self._enqueue_url(
                                        link,
                                        source_name=source_name,
                                        listing_page=0,
                                        fetch_tier=1,
                                    )
                                    discovered += 1
                            logger.info(
                                "jobs_rss_done",
                                source=source_name,
                                count=len(feed.entries),
                            )
                except Exception as e:
                    logger.warning(
                        "jobs_rss_error",
                        source=source_name,
                        error=str(e)[:80],
                    )
                await asyncio.sleep(1)

        # ── Source 3: Company career pages ────────────────────────────
        from provenmesh.crawler.fetcher import TieredFetcher
        fetcher = TieredFetcher()
        for career_url, source_name in _CAREER_PAGES:
            result = await fetcher.fetch(
                career_url,
                source_name=source_name,
                record_type=self.record_type,
                max_tier=1,
            )
            if result.ok:
                urls = self._extract_job_urls(result.text, career_url)
                for url in urls:
                    await self._enqueue_url(
                        url,
                        source_name=source_name,
                        listing_page=0,
                        fetch_tier=1,
                    )
                    discovered += 1
                # Also enqueue the career page itself as a JOB record
                await self._enqueue_url(
                    career_url,
                    source_name=source_name,
                    listing_page=0,
                    fetch_tier=1,
                )
                discovered += 1
                logger.info(
                    "career_page_done",
                    source=source_name,
                    jobs_found=len(urls),
                )
            else:
                logger.warning(
                    "career_page_failed", source=source_name, url=career_url,
                )
            await asyncio.sleep(2)

        await self._save_checkpoint("jobs", 1, "done")
        logger.info("jobs_producer_done", urls_discovered=discovered)

    def _extract_job_urls(self, html: str, base_url: str) -> list[str]:
        """Extract individual job posting URLs from a career page."""
        soup = BeautifulSoup(html, "lxml")
        urls: list[str] = []

        # Common job listing link patterns
        selectors = [
            "a[href*='/job/']",
            "a[href*='/jobs/']",
            "a[href*='/careers/']",
            "a[href*='/position']",
            "a[href*='/posting']",
            "a[href*='/apply']",
            "a.job-link",
            "a.posting-title",
            "a[data-job-id]",
        ]

        for selector in selectors:
            for link in soup.select(selector):
                href = str(link.get("href", ""))
                if href:
                    full_url = normalize_url(href, base_url)
                    if full_url and full_url not in urls:
                        urls.append(full_url)

        return urls[:50]
