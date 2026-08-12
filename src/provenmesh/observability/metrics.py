"""Prometheus-compatible metrics (PDF §10.1, v2 §35).

Tracks throughput, error rates per LLM tier, grounding failures,
freshness SLA compliance, and queue health. A threshold breach
(e.g., grounding failures > 5%) fires an alert.
"""

from __future__ import annotations

from prometheus_client import Counter, Gauge, Histogram, Info

# ─── Application Info ────────────────────────────────────────────

APP_INFO = Info("provenmesh", "ProvenMesh pipeline information")

# ─── Crawling Metrics ───────────────────────────────────────────

CRAWL_ITEMS_TOTAL = Counter(
    "provenmesh_crawl_items_total",
    "Total items discovered by producers",
    ["vertical", "source_name"],
)

CRAWL_SUCCESS_TOTAL = Counter(
    "provenmesh_crawl_success_total",
    "Successfully fetched items",
    ["vertical", "source_name", "fetch_tier"],
)

CRAWL_FAILURE_TOTAL = Counter(
    "provenmesh_crawl_failure_total",
    "Failed fetch attempts",
    ["vertical", "source_name", "error_type"],
)

FETCH_LATENCY = Histogram(
    "provenmesh_fetch_latency_seconds",
    "Fetch latency distribution",
    ["fetch_tier"],
    buckets=(0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0),
)

FETCH_TIER_TOTAL = Counter(
    "provenmesh_fetch_tier_total",
    "Fetch attempts by tier",
    ["tier"],
)

# ─── HTTP Error Metrics ─────────────────────────────────────────

HTTP_429_TOTAL = Counter(
    "provenmesh_http_429_total",
    "Rate limit (429) responses received",
    ["source"],
)

HTTP_413_TOTAL = Counter(
    "provenmesh_http_413_total",
    "Payload too large (413) responses received",
    ["source"],
)

HTTP_5XX_TOTAL = Counter(
    "provenmesh_http_5xx_total",
    "Server error (5xx) responses received",
    ["source"],
)

# ─── LLM Metrics ────────────────────────────────────────────────

LLM_REQUESTS_TOTAL = Counter(
    "provenmesh_llm_requests_total",
    "Total LLM extraction requests",
    ["provider"],
)

LLM_TOKENS_TOTAL = Counter(
    "provenmesh_llm_tokens_total",
    "Total tokens consumed",
    ["provider", "direction"],  # direction: input/output
)

LLM_COST_TOTAL = Counter(
    "provenmesh_llm_cost_usd_total",
    "Cumulative LLM cost in USD",
    ["provider"],
)

LLM_FALLBACK_TOTAL = Counter(
    "provenmesh_llm_fallback_total",
    "Fallback triggers from one provider to another",
    ["from_provider", "to_provider", "reason"],
)

LLM_LATENCY = Histogram(
    "provenmesh_llm_latency_seconds",
    "LLM call latency distribution",
    ["provider"],
    buckets=(0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0),
)

CIRCUIT_BREAKER_OPEN_TOTAL = Counter(
    "provenmesh_circuit_breaker_open_total",
    "Circuit breaker trips",
    ["provider"],
)

LLM_CACHE_HIT_TOTAL = Counter(
    "provenmesh_llm_cache_hit_total",
    "LLM response cache hits",
)

LLM_CACHE_MISS_TOTAL = Counter(
    "provenmesh_llm_cache_miss_total",
    "LLM response cache misses",
)

# ─── Grounding Metrics ──────────────────────────────────────────

GROUNDING_TOTAL = Counter(
    "provenmesh_grounding_total",
    "Total grounding verification attempts",
    ["field_type"],
)

GROUNDING_FAILURE_TOTAL = Counter(
    "provenmesh_grounding_failure_total",
    "Grounding verification failures",
    ["field_type"],
)

# ─── Entity Resolution Metrics ──────────────────────────────────

ENTITY_RESOLUTION_TOTAL = Counter(
    "provenmesh_entity_resolution_total",
    "Total entity resolution attempts",
    ["method"],  # exact, normalized, fuzzy, embedding
)

ENTITY_REVIEW_TOTAL = Counter(
    "provenmesh_entity_review_total",
    "Entities routed to human review",
)

# ─── Queue Metrics ──────────────────────────────────────────────

QUEUE_DEPTH = Gauge(
    "provenmesh_queue_depth",
    "Current queue depth",
    ["stream"],
)

QUEUE_OLDEST_MESSAGE_AGE = Gauge(
    "provenmesh_queue_oldest_message_age_seconds",
    "Age of the oldest unprocessed message",
    ["stream"],
)

# ─── Export Metrics ─────────────────────────────────────────────

EXPORT_SUCCESS_TOTAL = Counter(
    "provenmesh_export_success_total",
    "Successfully exported records",
    ["tab"],
)

EXPORT_FAILURE_TOTAL = Counter(
    "provenmesh_export_failure_total",
    "Failed export attempts",
    ["tab", "reason"],
)

# ─── Freshness SLA ──────────────────────────────────────────────

FRESHNESS_SLA_COMPLIANCE = Gauge(
    "provenmesh_freshness_sla_compliance",
    "Percentage of records meeting freshness SLA",
    ["vertical"],
)

# ─── Dedup Metrics ──────────────────────────────────────────────

DEDUP_HIT_TOTAL = Counter(
    "provenmesh_dedup_hit_total",
    "Items skipped due to deduplication",
    ["source"],
)

DEDUP_MISS_TOTAL = Counter(
    "provenmesh_dedup_miss_total",
    "New items passing dedup check",
    ["source"],
)

# ─── Cost Budget ────────────────────────────────────────────────

COST_BUDGET_UTILIZATION = Gauge(
    "provenmesh_cost_budget_utilization_pct",
    "Current budget utilization percentage",
)
