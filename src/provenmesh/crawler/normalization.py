"""URL and text normalization for crawling consistency."""

from __future__ import annotations

import re
from urllib.parse import urljoin, urlparse, urlunparse


def normalize_url(url: str, base_url: str = "") -> str:
    """Normalize a URL for consistent dedup and comparison.

    - Resolve relative URLs against base
    - Force lowercase scheme and netloc
    - Remove fragments
    - Remove trailing slashes (except root)
    - Sort query parameters
    - Remove common tracking parameters
    """
    if not url:
        return ""

    # Resolve relative URLs
    if base_url and not url.startswith(("http://", "https://")):
        url = urljoin(base_url, url)

    parsed = urlparse(url)

    # Force lowercase
    scheme = parsed.scheme.lower() or "https"
    netloc = parsed.netloc.lower()

    # Remove www prefix
    if netloc.startswith("www."):
        netloc = netloc[4:]

    # Remove trailing slash (keep root /)
    path = parsed.path
    if path != "/" and path.endswith("/"):
        path = path.rstrip("/")

    # Sort and filter query params
    tracking = {"utm_source", "utm_medium", "utm_campaign", "utm_term",
                "utm_content", "fbclid", "gclid", "ref", "source", "mc_cid",
                "mc_eid", "s_cid", "trk"}
    query = ""
    if parsed.query:
        params = sorted(
            p for p in parsed.query.split("&")
            if p.split("=")[0].lower() not in tracking
        )
        query = "&".join(params)

    return urlunparse((scheme, netloc, path, "", query, ""))


def extract_domain(url: str) -> str:
    """Extract the domain from a URL for rate limiting."""
    parsed = urlparse(url)
    domain = parsed.netloc.lower()
    if domain.startswith("www."):
        domain = domain[4:]
    return domain


def normalize_whitespace(text: str) -> str:
    """Collapse all whitespace to single spaces, strip edges."""
    return re.sub(r"\s+", " ", text).strip()


def extract_owner_repo(github_url: str) -> str:
    """Extract owner/repo from a GitHub URL (PDF §3.3)."""
    parsed = urlparse(github_url)
    parts = [p for p in parsed.path.strip("/").split("/") if p]
    if len(parts) >= 2:
        return f"{parts[0]}/{parts[1]}"
    return ""
