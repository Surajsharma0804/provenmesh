"""Input sanitization — clean untrusted data before processing."""

from __future__ import annotations

import html
import re
from urllib.parse import urlparse, urlunparse


def sanitize_url(url: str) -> str:
    """Canonicalize and sanitize a URL.

    - Strip tracking parameters (utm_*, fbclid, etc.)
    - Normalize scheme to https
    - Remove trailing slashes
    - Remove fragments
    """
    if not url:
        return ""

    parsed = urlparse(url.strip())

    # Force https
    scheme = "https" if parsed.scheme in ("http", "https", "") else parsed.scheme

    # Remove tracking params
    tracking_params = {"utm_source", "utm_medium", "utm_campaign", "utm_term",
                       "utm_content", "fbclid", "gclid", "ref", "source"}
    if parsed.query:
        params = parsed.query.split("&")
        clean_params = [
            p for p in params
            if p.split("=")[0].lower() not in tracking_params
        ]
        query = "&".join(clean_params)
    else:
        query = ""

    # Remove www prefix for consistency
    netloc = parsed.netloc.lower()
    if netloc.startswith("www."):
        netloc = netloc[4:]

    # Remove trailing slash
    path = parsed.path.rstrip("/") if parsed.path != "/" else ""

    return urlunparse((scheme, netloc, path, "", query, ""))


def sanitize_text(text: str) -> str:
    """Clean raw text for safe processing.

    - Decode HTML entities
    - Normalize whitespace
    - Remove null bytes and control characters
    """
    if not text:
        return ""

    # Decode HTML entities
    text = html.unescape(text)

    # Remove null bytes and control characters (keep newlines and tabs)
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)

    # Normalize whitespace (collapse multiple spaces, trim)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)

    return text.strip()


def sanitize_entity_name(name: str) -> str:
    """Normalize an entity name for matching.

    - Lowercase
    - Strip legal suffixes (Inc., Ltd, Corp, LLC, etc.)
    - Collapse whitespace
    - Strip punctuation edges
    """
    if not name:
        return ""

    name = name.strip().lower()

    # Strip common legal suffixes
    legal_suffixes = [
        r"\binc\.?\s*$", r"\binc\.?(?=\s|$)", r"\bltd\.?(?=\s|$)", r"\bcorp\.?(?=\s|$)",
        r"\bllc\.?(?=\s|$)", r"\bplc\.?(?=\s|$)", r"\bgmbh(?=\s|$)", r"\bco\.(?=\s|$)",
        r"\blimited(?=\s|$)", r"\bcorporation(?=\s|$)", r"\bcompany(?=\s|$)",
    ]
    for suffix in legal_suffixes:
        name = re.sub(suffix, "", name, flags=re.IGNORECASE)

    # Collapse whitespace
    name = re.sub(r"\s+", " ", name).strip()

    # Strip edge punctuation
    name = name.strip(".,;:!?-\u2014\u2013")

    return name.strip()
