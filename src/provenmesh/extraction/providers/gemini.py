"""Gemini Flash provider -- cheapest, fastest (PDF §5.1 priority 1)."""

from __future__ import annotations

import time

from google import genai
from google.genai import types as genai_types

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
    """Google Gemini Flash -- first in the fallback chain."""

    def __init__(self, model: str = "gemini-2.5-flash") -> None:
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

    def _get_client(self) -> genai.Client:
        settings = get_settings()
        api_key = safe_str(settings.gemini_api_key)
        if not api_key:
            raise LLMProviderError("GEMINI_API_KEY not configured", "gemini")
        return genai.Client(api_key=api_key)

    async def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        temperature: float = 0.0,
        max_tokens: int = 4096,
    ) -> LLMResponse:
        import asyncio
        client = self._get_client()
        start = time.monotonic()

        try:
            # Run the blocking SDK call in a thread to avoid blocking the event loop
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: client.models.generate_content(
                    model=self._model_name,
                    contents=user_prompt,
                    config=genai_types.GenerateContentConfig(
                        system_instruction=system_prompt,
                        temperature=temperature,
                        max_output_tokens=max_tokens,
                        response_mime_type="application/json",
                    ),
                ),
            )
            elapsed = (time.monotonic() - start) * 1000

            # Extract text safely
            raw_text = ""
            if response.candidates:
                candidate = response.candidates[0]
                if candidate.content and candidate.content.parts:
                    raw_text = "".join(
                        p.text for p in candidate.content.parts if hasattr(p, "text") and p.text
                    )
            if not raw_text and hasattr(response, "text") and response.text:
                raw_text = response.text

            # Extract token counts
            usage = response.usage_metadata
            input_tokens = getattr(usage, "prompt_token_count", 0) or 0
            output_tokens = getattr(usage, "candidates_token_count", 0) or 0

            cost = (
                (input_tokens / 1000) * self._cost_per_1k_input
                + (output_tokens / 1000) * self._cost_per_1k_output
            )

            finish_reason = ""
            if response.candidates:
                finish_reason = str(response.candidates[0].finish_reason)

            logger.debug(
                "gemini_response",
                model=self._model_name,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                finish_reason=finish_reason,
                preview=raw_text[:80],
            )

            return LLMResponse(
                content=raw_text,
                provider=self.provider_name,
                model=self._model_name,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                latency_ms=elapsed,
                cost_usd=cost,
                finish_reason=finish_reason,
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
