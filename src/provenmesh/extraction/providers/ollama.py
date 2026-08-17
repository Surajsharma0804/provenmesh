"""Ollama provider — local LLM with zero rate limits (v2 §14).

Ollama runs models locally on the user's GPU/CPU.
With RTX 2050 (4GB VRAM), recommended models:
  - llama3.2:3b  (fast, fits in 4GB)
  - phi3:mini    (3.8B, very fast)
  - qwen2.5:3b   (good JSON output)

Local models are PERFECT for extraction: the LLM reads already-crawled
page content and outputs structured JSON. It does NOT need internet
knowledge about the paper — it reads the page text directly.

No API key required. No rate limits. No cost. Runs 24/7.
"""

from __future__ import annotations

import time

import aiohttp

from provenmesh.extraction.providers.base import (
    BaseLLMProvider,
    ContextLengthError,
    LLMProviderError,
    LLMResponse,
)
from provenmesh.observability.logging import get_logger

logger = get_logger(__name__)

_OLLAMA_BASE_URL = "http://localhost:11434"
_DEFAULT_MODEL = "gemma3:4b"


class OllamaProvider(BaseLLMProvider):
    """Local Ollama LLM — last resort with NO rate limits.

    Placed last in the chain so cloud providers are used when available
    (higher quality), but Ollama ensures the pipeline NEVER fully stalls.
    Falls back gracefully if Ollama is not running.
    """

    def __init__(
        self,
        model: str = _DEFAULT_MODEL,
        base_url: str = _OLLAMA_BASE_URL,
    ) -> None:
        self._model_name = model
        self._base_url = base_url.rstrip("/")
        self._session: aiohttp.ClientSession | None = None

    @property
    def provider_name(self) -> str:
        return "ollama"

    @property
    def model_name(self) -> str:
        return self._model_name

    def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=120)  # Local = slower, allow 2min
            self._session = aiohttp.ClientSession(timeout=timeout)
        return self._session

    async def _is_available(self) -> bool:
        """Quick health check — returns False if Ollama isn't running."""
        try:
            async with self._get_session().get(
                f"{self._base_url}/api/tags", timeout=aiohttp.ClientTimeout(total=3)
            ) as resp:
                return resp.status == 200
        except Exception:
            return False

    async def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        temperature: float = 0.0,
        max_tokens: int = 4096,
    ) -> LLMResponse:
        # Fast availability check — skip entirely if Ollama isn't running
        if not await self._is_available():
            raise LLMProviderError(
                "Ollama not running. Start with: ollama serve",
                provider="ollama",
                retryable=False,
            )

        start = time.monotonic()

        payload = {
            "model": self._model_name,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
                "num_ctx": 8192,   # Context window
            },
            "format": "json",  # Ollama native JSON mode
        }

        try:
            async with self._get_session().post(
                f"{self._base_url}/api/chat",
                json=payload,
            ) as response:
                elapsed = (time.monotonic() - start) * 1000

                if response.status == 404:
                    # Model not pulled yet
                    raise LLMProviderError(
                        f"Model '{self._model_name}' not found. "
                        f"Run: ollama pull {self._model_name}",
                        provider="ollama",
                        retryable=False,
                    )

                if response.status != 200:
                    body = await response.text()
                    raise LLMProviderError(
                        f"Ollama HTTP {response.status}: {body[:200]}",
                        provider="ollama",
                    )

                data = await response.json()
                content = data.get("message", {}).get("content", "")

                # Ollama reports tokens in eval_count / prompt_eval_count
                input_tokens = data.get("prompt_eval_count", 0)
                output_tokens = data.get("eval_count", 0)

                logger.info(
                    "ollama_generation_complete",
                    model=self._model_name,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    elapsed_ms=round(elapsed, 1),
                )

                return LLMResponse(
                    content=content,
                    provider=self.provider_name,
                    model=self._model_name,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    latency_ms=elapsed,
                    cost_usd=0.0,  # Local = free
                    finish_reason=data.get("done_reason", "stop"),
                )

        except LLMProviderError:
            raise
        except aiohttp.ClientConnectorError as conn_err:
            raise LLMProviderError(
                "Cannot connect to Ollama. Start with: ollama serve",
                provider="ollama",
                retryable=False,
            ) from conn_err
        except Exception as e:
            elapsed = (time.monotonic() - start) * 1000
            error_str = str(e).lower()
            if "context" in error_str and "length" in error_str:
                raise ContextLengthError(str(e), "ollama") from e
            raise LLMProviderError(str(e), "ollama") from e

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None
