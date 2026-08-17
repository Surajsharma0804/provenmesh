"""Research papers producer -- ArXiv API direct access (PDF SS3.3).

Uses aiohttp directly to call ArXiv API, bypassing robots.txt gate
because this is a public data API, not a web scrape target.
"""

from __future__ import annotations

import asyncio
import xml.etree.ElementTree as ET
from pathlib import Path

import aiohttp
import yaml

from provenmesh.crawler.producers.base import BaseProducer
from provenmesh.observability.logging import get_logger

logger = get_logger(__name__)

_ARXIV_API_BASE = "https://export.arxiv.org/api/query"
_API_HEADERS = {
    "User-Agent": "ProvenMesh/1.0 (AI research pipeline)",
    "Accept": "application/xml, text/xml, */*",
}


def _load_arxiv_config() -> dict:
    """Load ArXiv API params from configs/sources.yaml."""
    # Walk up from this file to find the project root (contains configs/)
    here = Path(__file__).resolve()
    for parent in here.parents:
        cfg_path = parent / "configs" / "sources.yaml"
        if cfg_path.exists():
            try:
                data = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
                sources = data.get("verticals", {}).get("papers", {}).get("sources", [])
                arxiv = next((s for s in sources if s.get("name") == "arxiv_api"), {})
                return arxiv.get("api_params", {})
            except Exception as cfg_err:
                # Config load failure is non-fatal — ArXiv producer uses defaults
                logger.debug(
                    "arxiv_config_load_failed",
                    path=str(cfg_path),
                    error=str(cfg_err)[:80],
                )
    return {}


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

    # Full AI/CS/Engineering ArXiv category query — covers all fields:
    # AI, ML, NLP/LLMs, CV (facial/vision), Speech/Voice (eess.AS/cs.SD),
    # Robotics/Motion (cs.RO), Data Science (cs.DB/stat.ML),
    # HCI, Multimedia, Security, Signal Processing, Graphics
    _DEFAULT_QUERY = (
        "cat:cs.AI OR cat:cs.LG OR cat:cs.NE OR cat:stat.ML OR "
        "cat:cs.CL OR cat:cs.IR OR "
        "cat:cs.CV OR cat:cs.GR OR cat:eess.IV OR "
        "cat:cs.SD OR cat:eess.AS OR cat:eess.SP OR "
        "cat:cs.RO OR cat:cs.SY OR cat:eess.SY OR "
        "cat:cs.DB OR "
        "cat:cs.HC OR cat:cs.MM OR "
        "cat:cs.CR"
    )

    async def discover_urls(self) -> None:
        # Load ArXiv config from sources.yaml (with fallback to _DEFAULT_QUERY)
        api_params = _load_arxiv_config()

        search_query = api_params.get("search_query", self._DEFAULT_QUERY)
        # YAML multi-line folded scalars add newlines — strip them
        search_query = " ".join(search_query.split())

        batch_size = int(api_params.get("max_results", 200))
        max_crawl = 10_000  # total ceiling across all categories

        checkpoint = await self._load_checkpoint("papers")
        start_offset = checkpoint.get("page", 0) * batch_size

        discovered = 0
        timeout = aiohttp.ClientTimeout(total=30)

        async with aiohttp.ClientSession(timeout=timeout, headers=_API_HEADERS) as session:
            for offset in range(start_offset, max_crawl, batch_size):
                params = {
                    "search_query": search_query,
                    "sortBy": "submittedDate",
                    "sortOrder": "descending",
                    "start": offset,
                    "max_results": batch_size,
                }
                try:
                    async with session.get(_ARXIV_API_BASE, params=params) as response:
                        if response.status != 200:
                            logger.warning(
                                "arxiv_api_failed",
                                status=response.status,
                                offset=offset,
                            )
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
                logger.info(
                    "arxiv_batch_discovered",
                    offset=offset,
                    batch=len(paper_urls),
                    total=discovered,
                )
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
