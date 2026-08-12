"""DeepSeek provider — priority 3 last resort (PDF §5.1)."""

from __future__ import annotations

import time

from openai import AsyncOpenAI

from provenmesh.config.settings import get_settings
from provenmesh.extraction.providers.base import (
    BaseLLMProvider,
    ContextLengthError,
    LLMProviderError,
    LLMResponse,
    RateLimitError,
)
from provenmesh.observability.logging import get_logger
from provenmesh.security.secrets import safe_str

logger = get_logger(__name__)


class DeepSeekProvider(BaseLLMProvider):
    """DeepSeek — last resort in the fallback chain.

    Uses OpenAI-compatible API (PDF §14 tech stack).
    """

    def __init__(self, model: str = "deepseek-chat") -> None:
        self._model_name = model
        self._client: AsyncOpenAI | None = None
        self._cost_per_1k_input = 0.00014
        self._cost_per_1k_output = 0.00028

    @property
    def provider_name(self) -> str:
        return "deepseek"

    @property
    def model_name(self) -> str:
        return self._model_name

    def _get_client(self) -> AsyncOpenAI:
        if self._client is None:
            settings = get_settings()
            api_key = safe_str(settings.deepseek_api_key)
            if not api_key:
                raise LLMProviderError("DEEPSEEK_API_KEY not configured", "deepseek")
            self._client = AsyncOpenAI(
                api_key=api_key,
                base_url="https://api.deepseek.com/v1",
            )
        return self._client

    async def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        temperature: float = 0.0,
        max_tokens: int = 4096,
    ) -> LLMResponse:
        client = self._get_client()
        start = time.monotonic()

        try:
            response = await client.chat.completions.create(
                model=self._model_name,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=temperature,
                max_tokens=max_tokens,
                response_format={"type": "json_object"},
            )
            elapsed = (time.monotonic() - start) * 1000

            content = response.choices[0].message.content or "" if response.choices else ""
            usage = response.usage
            input_tokens = usage.prompt_tokens if usage else 0
            output_tokens = usage.completion_tokens if usage else 0

            cost = (
                (input_tokens / 1000) * self._cost_per_1k_input
                + (output_tokens / 1000) * self._cost_per_1k_output
            )

            return LLMResponse(
                content=content,
                provider=self.provider_name,
                model=self._model_name,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                latency_ms=elapsed,
                cost_usd=cost,
                finish_reason=response.choices[0].finish_reason or "" if response.choices else "",
            )

        except Exception as e:
            elapsed = (time.monotonic() - start) * 1000
            error_str = str(e).lower()

            if "429" in error_str or "rate" in error_str:
                raise RateLimitError(str(e), "deepseek") from e
            if "413" in error_str or "context" in error_str:
                raise ContextLengthError(str(e), "deepseek") from e

            raise LLMProviderError(str(e), "deepseek") from e

    async def close(self) -> None:
        if self._client:
            await self._client.close()
            self._client = None
