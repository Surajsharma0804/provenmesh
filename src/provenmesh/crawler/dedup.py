"""Distributed deduplication — atomic Redis SADD (PDF §4.3, v2 §8).

Key design: date-bucketed Redis keys instead of EXPIRE on entire sets.
    dedup:{source}:{date_bucket}
This makes expiration behavior predictable and bounded.

Fingerprint: SHA256(normalized_url + normalized_title + source)

Three-layer dedup (v2 §37):
    1. Redis SADD (fast, distributed)
    2. Queue-level (no re-enqueue of known URLs)
    3. PostgreSQL UNIQUE constraints (defense in depth)
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime

from provenmesh.config.settings import get_settings
from provenmesh.observability.logging import get_logger
from provenmesh.observability.metrics import DEDUP_HIT_TOTAL, DEDUP_MISS_TOTAL
from provenmesh.queue.streams import get_redis
from provenmesh.security.sanitization import sanitize_url

logger = get_logger(__name__)


def compute_dedup_hash(
    url: str,
    title: str = "",
    source: str = "",
) -> str:
    """Compute SHA-256 dedup fingerprint (PDF §4.3).

    Uses normalized URL + normalized title + source for uniqueness.
    """
    normalized_url = sanitize_url(url).lower()
    normalized_title = " ".join(title.lower().split())
    payload = f"{normalized_url}|{normalized_title}|{source}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def compute_content_hash(content: bytes | str) -> str:
    """Compute SHA-256 content hash for raw payload dedup.

    Same URL ≠ same content (v2 §8).
    """
    if isinstance(content, str):
        content = content.encode("utf-8")
    return hashlib.sha256(content).hexdigest()


def _get_date_bucket() -> str:
    """Get today's date bucket key in YYYY-MM-DD format."""
    return datetime.now(UTC).strftime("%Y-%m-%d")


async def is_duplicate(
    url: str,
    title: str = "",
    source_name: str = "",
) -> bool:
    """Check if an item has already been processed (atomic, distributed).

    Uses Redis SADD which atomically checks and adds — so two crawler
    nodes racing on the same URL cannot both win (PDF §4.3).

    Returns True if the item is a duplicate (already seen).
    """
    settings = get_settings()
    r = await get_redis()

    item_hash = compute_dedup_hash(url, title, source_name)
    date_bucket = _get_date_bucket()

    # Date-bucketed key (v2 §8 improvement)
    key = f"dedup:{source_name}:{date_bucket}"

    # Atomic SADD: returns 1 if newly added, 0 if duplicate
    is_new = await r.sadd(key, item_hash)

    if is_new:
        # Set TTL on the date bucket (30-day rolling window)
        await r.expire(key, settings.dedup_ttl_seconds)
        DEDUP_MISS_TOTAL.labels(source=source_name).inc()
        logger.debug("dedup_new_item", url=url, source=source_name)
        return False
    else:
        DEDUP_HIT_TOTAL.labels(source=source_name).inc()
        logger.debug("dedup_duplicate", url=url, source=source_name)
        return True


async def check_content_seen(
    content_hash: str,
    source_name: str = "",
) -> bool:
    """Check if content with this hash has already been processed.

    Prevents re-extraction of unchanged pages (same URL, same content).
    """
    r = await get_redis()
    key = f"content_seen:{source_name}"
    is_new = await r.sadd(key, content_hash)
    if is_new:
        await r.expire(key, get_settings().dedup_ttl_seconds)
        return False
    return True
