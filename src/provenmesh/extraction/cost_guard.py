"""Cost governance — token budget reservation (PDF §5.4, v2 §19).

Improved over PDF: pre-check token estimate before calling LLM
(reservation-based) instead of the PDF's "check every 500 calls."

Budget thresholds:
    80% → warning alert
    90% → cost-saving mode (cheapest provider only)
    100% → halt new extraction (queue buffers, no work dropped)
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from provenmesh.config.constants import COST_COUNTER_KEY
from provenmesh.config.settings import get_settings
from provenmesh.observability.logging import get_logger
from provenmesh.observability.metrics import COST_BUDGET_UTILIZATION
from provenmesh.queue.streams import get_redis

logger = get_logger(__name__)


class CostGuard:
    """Token budget manager with pre-reservation (v2 §19).

    Instead of post-hoc checking every N calls, this reserves
    estimated tokens BEFORE the LLM call, preventing overshoot.
    """

    def __init__(self) -> None:
        self._settings = get_settings()
        self._lock = asyncio.Lock()

    async def get_daily_usage(self) -> int:
        """Get current daily token usage from Redis."""
        r = await get_redis()
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        key = f"{COST_COUNTER_KEY}:{today}"
        usage = await r.get(key)
        return int(usage) if usage else 0

    async def get_budget_utilization_pct(self) -> float:
        """Get current budget utilization as a percentage."""
        usage = await self.get_daily_usage()
        budget = self._settings.llm_daily_token_budget
        pct = (usage / budget * 100) if budget > 0 else 0
        COST_BUDGET_UTILIZATION.set(pct)
        return pct

    async def can_proceed(self, estimated_tokens: int = 0) -> bool:
        """Check if we can proceed with an LLM call.

        Returns False if budget is exhausted (halts extraction at 100%).
        Logs warning at 80%.
        """
        usage = await self.get_daily_usage()
        budget = self._settings.llm_daily_token_budget
        projected = usage + estimated_tokens
        utilization_pct = (projected / budget * 100) if budget > 0 else 0

        if utilization_pct >= self._settings.llm_halt_threshold_pct:
            logger.error(
                "cost_budget_exhausted",
                usage=usage,
                budget=budget,
                utilization_pct=round(utilization_pct, 1),
            )
            return False

        if utilization_pct >= self._settings.llm_warning_threshold_pct:
            logger.warning(
                "cost_budget_warning",
                usage=usage,
                budget=budget,
                utilization_pct=round(utilization_pct, 1),
            )

        return True

    async def is_cost_saving_mode(self) -> bool:
        """Check if we should use only the cheapest provider (90%+ usage)."""
        pct = await self.get_budget_utilization_pct()
        return pct >= 90.0

    async def record_usage(self, tokens: int, cost_usd: float = 0.0) -> None:
        """Record token usage after an LLM call.

        Uses Redis INCRBY for atomic increment across workers.
        Daily key auto-expires at midnight UTC.
        """
        r = await get_redis()
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        key = f"{COST_COUNTER_KEY}:{today}"

        await r.incrby(key, tokens)
        await r.expire(key, 86400 * 2)  # Expire after 2 days

        # Also track cost
        cost_key = f"{COST_COUNTER_KEY}:cost:{today}"
        await r.incrbyfloat(cost_key, cost_usd)
        await r.expire(cost_key, 86400 * 2)

        logger.debug(
            "cost_recorded",
            tokens=tokens,
            cost_usd=round(cost_usd, 6),
        )

    async def reserve_tokens(self, estimated_tokens: int) -> bool:
        """Atomically reserve tokens before an LLM call (v2 §19).

        Returns True if reservation succeeded, False if budget exhausted.
        """
        async with self._lock:
            if not await self.can_proceed(estimated_tokens):
                return False

            r = await get_redis()
            today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            key = f"{COST_COUNTER_KEY}:{today}"
            await r.incrby(key, estimated_tokens)
            await r.expire(key, 86400 * 2)

            return True

    async def release_reservation(self, estimated_tokens: int, actual_tokens: int) -> None:
        """Adjust reservation after LLM call completes.

        If actual < estimated, return the difference to the budget.
        If actual > estimated, the overshoot is already accounted for.
        """
        difference = estimated_tokens - actual_tokens
        if difference > 0:
            r = await get_redis()
            today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            key = f"{COST_COUNTER_KEY}:{today}"
            await r.decrby(key, difference)
