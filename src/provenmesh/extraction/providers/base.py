"""LLM provider base — abstract interface for all LLM providers.

All providers implement the same interface so they are interchangeable
in the fallback chain. Contract tests verify this (tests/contract/).
"""

from __future__ import annotations

import abc
from dataclasses import dataclass


@dataclass(frozen=True)
class LLMResponse:
    """Standardized response from any LLM provider."""

    content: str
    provider: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    latency_ms: float = 0.0
    cost_usd: float = 0.0
    cached: bool = False
    finish_reason: str = ""

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


class LLMProviderError(Exception):
    """Base error for LLM provider failures."""

    def __init__(self, message: str, provider: str = "", retryable: bool = True) -> None:
        super().__init__(message)
        self.provider = provider
        self.retryable = retryable


class RateLimitError(LLMProviderError):
    """429 rate limit from provider."""

    def __init__(self, message: str, provider: str = "", retry_after: float | None = None) -> None:
        super().__init__(message, provider, retryable=True)
        self.retry_after = retry_after


class ContextLengthError(LLMProviderError):
    """413 payload too large."""

    def __init__(self, message: str, provider: str = "") -> None:
        super().__init__(message, provider, retryable=False)


class BaseLLMProvider(abc.ABC):
    """Abstract base for LLM providers.

    All providers in the fallback chain implement this interface.
    This enables contract testing (same tests run against all providers).
    """

    @property
    @abc.abstractmethod
    def provider_name(self) -> str:
        """Provider identifier (e.g., 'gemini', 'groq', 'deepseek')."""
        ...

    @property
    @abc.abstractmethod
    def model_name(self) -> str:
        """Model identifier."""
        ...

    @abc.abstractmethod
    async def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        temperature: float = 0.0,
        max_tokens: int = 4096,
    ) -> LLMResponse:
        """Generate a completion from the model.

        Raises:
            RateLimitError: 429 from provider.
            ContextLengthError: 413 from provider.
            LLMProviderError: Other provider errors.
        """
        ...

    @abc.abstractmethod
    async def close(self) -> None:
        """Clean up provider resources."""
        ...
