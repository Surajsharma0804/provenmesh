"""Gemini Flash provider — cheapest, fastest (PDF §5.1 priority 1)."""

from __future__ import annotations

import time

import google.generativeai as genai

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


class GeminiProvider(BaseLLMProvider):
    """Google Gemini Flash — first in the fallback chain."""

    def __init__(self, model: str = "gemini-2.0-flash") -> None:
        self._model_name = model
        self._configured = False
        self._cost_per_1k_input = 0.000075
        self._cost_per_1k_output = 0.0003

    @property
    def provider_name(self) -> str:
        return "gemini"

    @property
    def model_name(self) -> str:
        return self._model_name

    def _ensure_configured(self) -> None:
        if not self._configured:
            settings = get_settings()
            api_key = safe_str(settings.gemini_api_key)
            if not api_key:
                raise LLMProviderError("GEMINI_API_KEY not configured", "gemini")
            genai.configure(api_key=api_key)
            self._configured = True

    async def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        temperature: float = 0.0,
        max_tokens: int = 4096,
    ) -> LLMResponse:
        self._ensure_configured()
        start = time.monotonic()

        try:
            model = genai.GenerativeModel(
                model_name=self._model_name,
                system_instruction=system_prompt,
                generation_config=genai.GenerationConfig(
                    temperature=temperature,
                    max_output_tokens=max_tokens,
                    response_mime_type="application/json",
                ),
            )

            response = model.generate_content(user_prompt)
            elapsed = (time.monotonic() - start) * 1000

            # Extract token counts
            usage = response.usage_metadata
            input_tokens = usage.prompt_token_count if usage else 0
            output_tokens = usage.candidates_token_count if usage else 0

            cost = (
                (input_tokens / 1000) * self._cost_per_1k_input
                + (output_tokens / 1000) * self._cost_per_1k_output
            )

            return LLMResponse(
                content=response.text or "",
                provider=self.provider_name,
                model=self._model_name,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                latency_ms=elapsed,
                cost_usd=cost,
                finish_reason=str(response.candidates[0].finish_reason) if response.candidates else "",  # noqa: E501
            )

        except Exception as e:
            elapsed = (time.monotonic() - start) * 1000
            error_str = str(e).lower()

            if "429" in error_str or "rate" in error_str or "quota" in error_str:
                raise RateLimitError(str(e), "gemini") from e
            if "413" in error_str or "too large" in error_str or "token" in error_str:
                raise ContextLengthError(str(e), "gemini") from e

            raise LLMProviderError(str(e), "gemini") from e

    async def close(self) -> None:
        pass
