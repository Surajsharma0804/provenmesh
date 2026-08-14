"""Research papers producer -- ArXiv API direct access (PDF SS3.3).

Uses aiohttp directly to call ArXiv API, bypassing robots.txt gate
because this is a public data API, not a web scrape target.
"""

from __future__ import annotations

import asyncio
import xml.etree.ElementTree as ET

import aiohttp

from provenmesh.crawler.producers.base import BaseProducer
from provenmesh.observability.logging import get_logger

logger = get_logger(__name__)

_ARXIV_API_BASE = "https://export.arxiv.org/api/query"
_API_HEADERS = {
    "User-Agent": "ProvenMesh/1.0 (AI research pipeline)",
    "Accept": "application/xml, text/xml, */*",
}


class PapersProducer(BaseProducer):
    """Discovers AI research papers via the ArXiv REST API.

    Calls ArXiv API directly with aiohttp -- bypasses the robots checker
    because the ArXiv API is a public data endpoint, not a scrape target.
    """

    @property
    def vertical_name(self) -> str:
        return "papers"

    @property
    def record_type(self) -> str:
        return "PAPER"

    async def discover_urls(self) -> None:
        checkpoint = await self._load_checkpoint("papers")
        start_offset = checkpoint.get("page", 0) * 100

        batch_size = 100
        max_results = 2000
        discovered = 0
        timeout = aiohttp.ClientTimeout(total=30)

        async with aiohttp.ClientSession(timeout=timeout, headers=_API_HEADERS) as session:
            for offset in range(start_offset, max_results, batch_size):
                params = {
                    "search_query": "cat:cs.AI OR cat:cs.LG OR cat:cs.CL",
                    "sortBy": "submittedDate",
                    "sortOrder": "descending",
                    "start": offset,
                    "max_results": batch_size,
                }
                try:
                    async with session.get(_ARXIV_API_BASE, params=params) as response:
                        if response.status != 200:
                            logger.warning("arxiv_api_failed", status=response.status, offset=offset)
                            break
                        xml_text = await response.text()
                except Exception as e:
                    logger.warning("arxiv_fetch_error", error=str(e), offset=offset)
                    break

                paper_urls = self._parse_arxiv_response(xml_text)
                if not paper_urls:
                    logger.info("arxiv_no_more_results", offset=offset)
                    break

                for url in paper_urls:
                    await self._enqueue_url(
                        url,
                        source_name="arxiv_api",
                        listing_page=offset // batch_size,
                        fetch_tier=1,
                    )
                    discovered += 1

                await self._save_checkpoint("papers", offset // batch_size, _ARXIV_API_BASE)
                logger.info("arxiv_batch_discovered", offset=offset, batch=len(paper_urls), total=discovered)
                await asyncio.sleep(3)  # polite delay between API requests

        logger.info("papers_producer_done", urls_discovered=discovered)

    def _parse_arxiv_response(self, xml_text: str) -> list[str]:
        """Parse ArXiv API XML response to extract paper abstract URLs."""
        urls: list[str] = []
        try:
            root = ET.fromstring(xml_text)  # noqa: S314
            ns = {"atom": "http://www.w3.org/2005/Atom"}
            for entry in root.findall("atom:entry", ns):
                found = False
                for link in entry.findall("atom:link", ns):
                    href = link.get("href", "")
                    if href and "/abs/" in href:
                        urls.append(href)
                        found = True
                        break
                if not found:
                    id_elem = entry.find("atom:id", ns)
                    if id_elem is not None and id_elem.text:
                        raw = id_elem.text
                        arxiv_id = raw.split("/abs/")[-1] if "/abs/" in raw else raw.split("/")[-1]
                        if arxiv_id:
                            urls.append(f"https://arxiv.org/abs/{arxiv_id}")
        except ET.ParseError as e:
            logger.error("arxiv_xml_parse_error", error=str(e))
        return urls
