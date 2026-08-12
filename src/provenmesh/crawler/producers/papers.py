"""Research papers producer — ArXiv API + GitHub enrichment (PDF §3.3).

Primary: ArXiv API (structured, no scraping required for metadata).
Enrichment: GitHub REST API for star counts and repository links.
Secondary: paperswithcode.co for code-paper linkage (secondary only).
"""

from __future__ import annotations

import xml.etree.ElementTree as ET

from provenmesh.crawler.fetcher import TieredFetcher
from provenmesh.crawler.producers.base import BaseProducer
from provenmesh.observability.logging import get_logger

logger = get_logger(__name__)


class PapersProducer(BaseProducer):
    """Discovers AI research papers via ArXiv API.

    The PDF specifically recommends treating paperswithcode.co as
    secondary enrichment rather than the primary paper source (§3.3).
    """

    @property
    def vertical_name(self) -> str:
        return "papers"

    @property
    def record_type(self) -> str:
        return "PAPER"

    async def discover_urls(self) -> None:
        fetcher = TieredFetcher()
        checkpoint = await self._load_checkpoint("papers")
        start_offset = checkpoint.get("page", 0) * 100

        # ArXiv API — structured, no scraping required (PDF §3.3)
        batch_size = 100
        max_results = 5000

        for offset in range(start_offset, max_results, batch_size):
            api_url = (
                f"https://export.arxiv.org/api/query"
                f"?search_query=cat:cs.AI+OR+cat:cs.LG+OR+cat:cs.CL"
                f"&sortBy=submittedDate"
                f"&sortOrder=descending"
                f"&start={offset}"
                f"&max_results={batch_size}"
            )

            result = await fetcher.fetch(
                api_url,
                source_name="arxiv_api",
                record_type=self.record_type,
                max_tier=1,  # API — no escalation needed
            )

            if not result.ok:
                logger.warning("arxiv_api_failed", status=result.status, offset=offset)
                break

            paper_urls = self._parse_arxiv_response(result.text)
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

            page_num = offset // batch_size
            await self._save_checkpoint("papers", page_num, api_url)

    def _parse_arxiv_response(self, xml_text: str) -> list[str]:
        """Parse ArXiv API XML response to extract paper URLs."""
        urls: list[str] = []
        try:
            root = ET.fromstring(xml_text)
            ns = {"atom": "http://www.w3.org/2005/Atom"}

            for entry in root.findall("atom:entry", ns):
                # Get the abstract page URL
                for link in entry.findall("atom:link", ns):
                    href = link.get("href", "")
                    link_type = link.get("type", "")
                    if href and "abs" in href:
                        urls.append(href)
                        break

                # Fallback: construct from arxiv ID
                if not urls or urls[-1] == "":
                    id_elem = entry.find("atom:id", ns)
                    if id_elem is not None and id_elem.text:
                        arxiv_id = id_elem.text.split("/")[-1]
                        urls.append(f"https://arxiv.org/abs/{arxiv_id}")

        except ET.ParseError as e:
            logger.error("arxiv_xml_parse_error", error=str(e))

        return urls
