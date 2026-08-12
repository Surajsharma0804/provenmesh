"""Application constants — values that never change at runtime."""

from __future__ import annotations

# ─── Schema ──────────────────────────────────────────────────────
SCHEMA_VERSION = "1.0"
PROMPT_VERSION = 4  # Bump when extraction prompts change

# ─── Queue Stream Names ─────────────────────────────────────────
DISCOVERY_STREAM = "provenmesh:discovery"
EXTRACTION_STREAM = "provenmesh:extraction"
RESOLUTION_STREAM = "provenmesh:resolution"
EXPORT_STREAM = "provenmesh:export"

# DLQ streams (v2 §12)
CRAWL_DLQ = "provenmesh:dlq:crawl"
EXTRACTION_DLQ = "provenmesh:dlq:extraction"
RESOLUTION_DLQ = "provenmesh:dlq:resolution"
EXPORT_DLQ = "provenmesh:dlq:export"

# ─── Consumer Groups ────────────────────────────────────────────
CRAWL_CONSUMER_GROUP = "crawl-workers"
EXTRACTION_CONSUMER_GROUP = "extraction-workers"
RESOLUTION_CONSUMER_GROUP = "resolution-workers"
EXPORT_CONSUMER_GROUP = "export-workers"

# ─── Redis Key Prefixes ─────────────────────────────────────────
DEDUP_KEY_PREFIX = "dedup"
CHECKPOINT_KEY_PREFIX = "checkpoint"
RATE_LIMIT_KEY_PREFIX = "ratelimit"
CIRCUIT_BREAKER_KEY_PREFIX = "circuit"
LLM_CACHE_KEY_PREFIX = "llmcache"
COST_COUNTER_KEY = "provenmesh:cost:daily"
BACKPRESSURE_KEY = "provenmesh:backpressure"

# ─── S3 Key Patterns ────────────────────────────────────────────
RAW_STORE_PREFIX = "raw"  # raw/{source}/{YYYY}/{MM}/{DD}/{content_hash}/

# ─── HTTP Headers ────────────────────────────────────────────────
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:128.0) Gecko/20100101 Firefox/128.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36 Edg/125.0.0.0",
]

# ─── Timeouts ────────────────────────────────────────────────────
DEFAULT_HTTP_TIMEOUT = 30
PLAYWRIGHT_TIMEOUT = 45
PROXY_TIMEOUT = 60

# ─── Export Tab Names (PDF §12) ──────────────────────────────────
SHEETS_TAB_ORDER = [
    "Startups",
    "Products",
    "Papers",
    "Jobs",
    "News",
    "Entity Mapping Log",
]
