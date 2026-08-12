"""LLM response cache — versioned by content+schema+prompt+model (v2 §18).

Cache key: SHA256(content_hash + schema_version + prompt_version + model)
TTL: 24 hours (PDF §5.4).

Prevents stale responses after schema/prompt changes.
"""

from __future__ import annotations

import hashlib
import json

from provenmesh.config.constants import PROMPT_VERSION, SCHEMA_VERSION
from provenmesh.config.settings import get_settings
from provenmesh.observability.logging import get_logger
from provenmesh.observability.metrics import LLM_CACHE_HIT_TOTAL, LLM_CACHE_MISS_TOTAL
from provenmesh.queue.streams import get_redis

logger = get_logger(__name__)

_KEY_PREFIX = "llmcache"


def _build_cache_key(
    content_hash: str,
    model: str,
    record_type: str,
) -> str:
    """Build versioned cache key (v2 §18).

    Includes schema_version + prompt_version so cache invalidates
    automatically when extraction logic changes.
    """
    components = f"{content_hash}:{SCHEMA_VERSION}:{PROMPT_VERSION}:{model}:{record_type}"
    key_hash = hashlib.sha256(components.encode()).hexdigest()[:32]
    return f"{_KEY_PREFIX}:v{SCHEMA_VERSION}:{key_hash}"


async def get_cached_response(
    content_hash: str,
    model: str,
    record_type: str,
) -> dict | None:
    """Check cache for a previous LLM extraction result.

    Returns the cached JSON response or None on miss.
    """
    r = await get_redis()
    key = _build_cache_key(content_hash, model, record_type)

    cached = await r.get(key)
    if cached:
        LLM_CACHE_HIT_TOTAL.inc()
        logger.debug("llm_cache_hit", content_hash=content_hash[:16], model=model)
        data = cached.decode("utf-8") if isinstance(cached, bytes) else cached
        return json.loads(data)

    LLM_CACHE_MISS_TOTAL.inc()
    return None


async def set_cached_response(
    content_hash: str,
    model: str,
    record_type: str,
    response_data: dict,
) -> None:
    """Cache an LLM extraction result.

    TTL: 24 hours — re-crawled but unchanged pages never trigger
    a second LLM call (PDF §5.4).
    """
    r = await get_redis()
    settings = get_settings()
    key = _build_cache_key(content_hash, model, record_type)

    await r.setex(
        key,
        settings.llm_cache_ttl_seconds,
        json.dumps(response_data),
    )

    logger.debug(
        "llm_cache_set",
        content_hash=content_hash[:16],
        model=model,
        ttl=settings.llm_cache_ttl_seconds,
    )
