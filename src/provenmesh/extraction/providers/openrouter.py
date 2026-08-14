"""OpenRouter provider -- free-tier models via OpenAI-compatible API.

Fallback priority 3 (after Gemini -> Groq -> OpenRouter -> DeepSeek).

Free models available on OpenRouter (no billing required):
  - meta-llama/llama-3.1-8b-instruct:free
  - mistralai/mistral-7b-instruct:free
  - google/gemma-2-9b-it:free

Sign up at: https://openrouter.ai  ->  API Keys  ->  Create Key
"""

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

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"


class OpenRouterProvider(BaseLLMProvider):
    """OpenRouter -- free LLM gateway, third in the fallback chain."""

    def __init__(self, model: str = "google/gemma-4-31b-it:free") -> None:
        self._model_name = model
        self._client: AsyncOpenAI | None = None
        self._cost_per_1k_input = 0.0
        self._cost_per_1k_output = 0.0

    @property
    def provider_name(self) -> str:
        return "openrouter"

    @property
    def model_name(self) -> str:
        return self._model_name

    def _get_client(self) -> AsyncOpenAI:
        if self._client is None:
            settings = get_settings()
            api_key = safe_str(settings.openrouter_api_key)
            if not api_key:
                raise LLMProviderError("OPENROUTER_API_KEY not configured", "openrouter")
            self._client = AsyncOpenAI(
                api_key=api_key,
                base_url=OPENROUTER_BASE_URL,
                default_headers={
                    "HTTP-Referer": "https://github.com/provenmesh",
                    "X-Title": "ProvenMesh Intelligence Graph",
                },
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

            content = ""
            if response.choices:
                content = response.choices[0].message.content or ""

            usage = response.usage
            input_tokens = usage.prompt_tokens if usage else 0
            output_tokens = usage.completion_tokens if usage else 0

            logger.debug(
                "openrouter_response",
                model=self._model_name,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
            )

            return LLMResponse(
                content=content,
                provider=self.provider_name,
                model=self._model_name,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                latency_ms=elapsed,
                cost_usd=0.0,
                finish_reason=response.choices[0].finish_reason or "" if response.choices else "",
            )

        except Exception as e:
            error_str = str(e).lower()
            if "429" in error_str or "rate" in error_str:
                raise RateLimitError(str(e), "openrouter") from e
            if "413" in error_str or "context" in error_str:
                raise ContextLengthError(str(e), "openrouter") from e
            raise LLMProviderError(str(e), "openrouter") from e

    async def close(self) -> None:
        if self._client:
            await self._client.close()
            self._client = None
