"""LLM Orchestrator — fallback chain with circuit breakers (PDF §5.1, v2 §14-15).

Fallback chain: Gemini Flash → Groq Llama 3 → DeepSeek
Each tier gets exponential backoff with jitter; a circuit breaker
trips a tier out of rotation for 60s after 5 consecutive failures.
"""

from __future__ import annotations

import asyncio
import time

from provenmesh.config.settings import get_settings
from provenmesh.domain.enums import CircuitState
from provenmesh.extraction.cache import get_cached_response, set_cached_response
from provenmesh.extraction.chunking import chunk_text, estimate_tokens, extract_main_content
from provenmesh.extraction.cost_guard import CostGuard
from provenmesh.extraction.parser import (
    extract_evidenced_fields,
    extract_relationships,
    parse_llm_response,
)
from provenmesh.extraction.prompts import EXTRACTION_PROMPTS, SYSTEM_PROMPT
from provenmesh.extraction.providers.base import (
    BaseLLMProvider,
    ContextLengthError,
    LLMProviderError,
    LLMResponse,
    RateLimitError,
)
from provenmesh.extraction.providers.deepseek import DeepSeekProvider
from provenmesh.extraction.providers.gemini import GeminiProvider
from provenmesh.extraction.providers.groq import GroqProvider
from provenmesh.observability.logging import get_logger
from provenmesh.observability.metrics import (
    CIRCUIT_BREAKER_OPEN_TOTAL,
    LLM_COST_TOTAL,
    LLM_FALLBACK_TOTAL,
    LLM_LATENCY,
    LLM_REQUESTS_TOTAL,
    LLM_TOKENS_TOTAL,
)

logger = get_logger(__name__)


class CircuitBreaker:
    """Per-provider circuit breaker (PDF §5.1, v2 §15).

    CLOSED → 5 failures → OPEN → 60s → HALF_OPEN → success → CLOSED
    """

    def __init__(self, failure_threshold: int = 5, recovery_timeout: float = 60.0) -> None:
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._failure_threshold = failure_threshold
        self._recovery_timeout = recovery_timeout
        self._last_failure_time = 0.0
        self._half_open_requests = 0

    @property
    def state(self) -> CircuitState:
        is_open = self._state == CircuitState.OPEN
        elapsed = time.monotonic() - self._last_failure_time
        if is_open and elapsed >= self._recovery_timeout:
            self._state = CircuitState.HALF_OPEN
            self._half_open_requests = 0
        return self._state

    def record_success(self) -> None:
        self._failure_count = 0
        self._state = CircuitState.CLOSED

    def record_failure(self, provider: str) -> None:
        self._failure_count += 1
        self._last_failure_time = time.monotonic()
        if self._failure_count >= self._failure_threshold:
            self._state = CircuitState.OPEN
            CIRCUIT_BREAKER_OPEN_TOTAL.labels(provider=provider).inc()
            logger.warning(
                "circuit_breaker_opened",
                provider=provider,
                failures=self._failure_count,
            )

    @property
    def is_available(self) -> bool:
        state = self.state
        if state == CircuitState.CLOSED:
            return True
        if state == CircuitState.HALF_OPEN and self._half_open_requests < 2:
            self._half_open_requests += 1
            return True
        return False


class ExtractionOrchestrator:  # pragma: no cover
    """Multi-provider LLM orchestrator with fallback, caching, and cost control.

    This is the central intelligence engine — coordinates chunking,
    LLM calls, response parsing, and cost governance.
    """

    def __init__(self) -> None:
        self._settings = get_settings()
        self._cost_guard = CostGuard()
        self._providers: list[BaseLLMProvider] = [
            GeminiProvider(),
            GroqProvider(),
            DeepSeekProvider(),
        ]
        self._circuit_breakers: dict[str, CircuitBreaker] = {
            p.provider_name: CircuitBreaker(
                failure_threshold=self._settings.circuit_breaker_failure_threshold,
                recovery_timeout=self._settings.circuit_breaker_recovery_timeout_seconds,
            )
            for p in self._providers
        }

    async def extract(
        self,
        html_content: str,
        record_type: str,
        content_hash: str,
        source_url: str = "",
    ) -> dict:
        """Extract structured data from HTML content.

        Returns dict with:
            - fields: evidence-first extracted fields
            - relationships: discovered relationship candidates
            - provider: which provider was used
            - tokens: total tokens consumed
            - cost: USD cost
            - cached: whether result came from cache
        """
        # Check cache first
        for provider in self._providers:
            cached = await get_cached_response(content_hash, provider.model_name, record_type)
            if cached:
                return {**cached, "cached": True, "provider": provider.provider_name}

        # Check cost budget
        estimated_tokens = estimate_tokens(html_content) * 2  # Input + output
        if not await self._cost_guard.can_proceed(estimated_tokens):
            logger.warning("extraction_blocked_by_budget", content_hash=content_hash[:16])
            return {"fields": {}, "relationships": [], "error": "budget_exhausted"}

        # Reserve tokens
        reserved = await self._cost_guard.reserve_tokens(estimated_tokens)
        if not reserved:
            return {"fields": {}, "relationships": [], "error": "budget_exhausted"}

        # Extract main content and chunk
        main_text = extract_main_content(html_content)
        prompt_template = EXTRACTION_PROMPTS.get(record_type, EXTRACTION_PROMPTS["STARTUP"])

        chunks = chunk_text(main_text, max_tokens=3000)
        all_fields: dict = {}
        all_relationships: list = []
        total_tokens = 0
        total_cost = 0.0
        provider_used = ""

        try:
            for chunk in chunks:
                user_prompt = prompt_template.format(content=chunk.text)
                response = await self._call_with_fallback(user_prompt, record_type)

                if response:
                    parsed = parse_llm_response(response.content)
                    fields = extract_evidenced_fields(parsed)
                    relationships = extract_relationships(parsed)

                    # Merge fields (structured markup wins — v2 §17)
                    for key, value in fields.items():
                        if key not in all_fields or chunk.has_structured_markup:
                            all_fields[key] = value

                    all_relationships.extend(relationships)
                    total_tokens += response.total_tokens
                    total_cost += response.cost_usd
                    provider_used = response.provider

            result = {
                "fields": all_fields,
                "relationships": all_relationships,
                "provider": provider_used,
                "tokens": total_tokens,
                "cost": total_cost,
                "cached": False,
            }

            # Cache the result
            if all_fields:
                await set_cached_response(content_hash, provider_used, record_type, result)

            # Release reservation and record actual usage
            await self._cost_guard.release_reservation(estimated_tokens, total_tokens)
            await self._cost_guard.record_usage(total_tokens, total_cost)

            return result

        except Exception as e:
            await self._cost_guard.release_reservation(estimated_tokens, 0)
            logger.error("extraction_failed", error=str(e), content_hash=content_hash[:16])
            return {"fields": {}, "relationships": [], "error": str(e)}

    async def _call_with_fallback(
        self,
        user_prompt: str,
        record_type: str,
    ) -> LLMResponse | None:
        """Call LLM with fallback chain and circuit breakers.

        Tries each provider in order. On 429/5xx, falls back to next.
        Circuit breaker skips providers that are failing consistently.
        """
        cost_saving = await self._cost_guard.is_cost_saving_mode()

        for i, provider in enumerate(self._providers):
            cb = self._circuit_breakers[provider.provider_name]

            if not cb.is_available:
                logger.debug("provider_circuit_open", provider=provider.provider_name)
                continue

            # In cost-saving mode, only use the cheapest provider
            if cost_saving and i > 0:
                logger.info("cost_saving_mode_skip", provider=provider.provider_name)
                continue

            try:
                LLM_REQUESTS_TOTAL.labels(provider=provider.provider_name).inc()
                start = time.monotonic()

                response = await provider.generate(
                    system_prompt=SYSTEM_PROMPT,
                    user_prompt=user_prompt,
                    temperature=0.0,
                    max_tokens=4096,
                )

                elapsed = (time.monotonic() - start) * 1000
                LLM_LATENCY.labels(provider=provider.provider_name).observe(elapsed / 1000)
                LLM_TOKENS_TOTAL.labels(
                    provider=provider.provider_name, direction="input",
                ).inc(response.input_tokens)
                LLM_TOKENS_TOTAL.labels(
                    provider=provider.provider_name, direction="output",
                ).inc(response.output_tokens)
                LLM_COST_TOTAL.labels(provider=provider.provider_name).inc(response.cost_usd)

                cb.record_success()
                return response

            except RateLimitError as e:
                cb.record_failure(provider.provider_name)
                next_idx = i + 1
                next_provider = (
                    self._providers[next_idx].provider_name
                    if next_idx < len(self._providers)
                    else "none"
                )
                LLM_FALLBACK_TOTAL.labels(
                    from_provider=provider.provider_name,
                    to_provider=next_provider,
                    reason="rate_limit",
                ).inc()
                logger.warning(
                    "llm_rate_limited",
                    provider=provider.provider_name,
                    retry_after=e.retry_after,
                )

                # Honor Retry-After if this is the last provider
                if i == len(self._providers) - 1 and e.retry_after:
                    await asyncio.sleep(min(e.retry_after, 30))

            except ContextLengthError:
                logger.warning("llm_context_exceeded", provider=provider.provider_name)
                # Don't fallback for 413 — the content is too large for all providers
                return None

            except LLMProviderError as e:
                cb.record_failure(provider.provider_name)
                logger.warning(
                    "llm_provider_error",
                    provider=provider.provider_name,
                    error=str(e),
                )

        logger.error("all_llm_providers_exhausted")
        return None

    async def close(self) -> None:
        """Clean up all provider resources."""
        for provider in self._providers:
            await provider.close()
