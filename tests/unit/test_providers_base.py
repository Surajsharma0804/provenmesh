"""Tests for extraction/providers/base.py — LLM provider base classes."""
from __future__ import annotations

import pytest

from provenmesh.extraction.providers.base import (
    ContextLengthError,
    LLMProviderError,
    LLMResponse,
    RateLimitError,
)


class TestLLMResponse:
    def test_creation(self) -> None:
        r = LLMResponse(
            content='{"entityName": "test"}',
            provider="gemini",
            model="gemini-1.5-flash",
            input_tokens=100,
            output_tokens=50,
        )
        assert r.content == '{"entityName": "test"}'
        assert r.provider == "gemini"

    def test_total_tokens(self) -> None:
        r = LLMResponse(
            content="", provider="test", model="m",
            input_tokens=100, output_tokens=50,
        )
        assert r.total_tokens == 150

    def test_defaults(self) -> None:
        r = LLMResponse(content="", provider="p", model="m")
        assert r.input_tokens == 0
        assert r.output_tokens == 0
        assert r.latency_ms == 0.0
        assert r.cost_usd == 0.0
        assert r.cached is False
        assert r.finish_reason == ""

    def test_frozen(self) -> None:
        r = LLMResponse(content="", provider="p", model="m")
        with pytest.raises(AttributeError, match="cannot assign"):
            r.content = "new"  # type: ignore


class TestLLMProviderError:
    def test_basic(self) -> None:
        err = LLMProviderError("test error", provider="gemini")
        assert str(err) == "test error"
        assert err.provider == "gemini"
        assert err.retryable is True

    def test_not_retryable(self) -> None:
        err = LLMProviderError("bad", retryable=False)
        assert err.retryable is False


class TestRateLimitError:
    def test_basic(self) -> None:
        err = RateLimitError("rate limited", provider="groq", retry_after=30.0)
        assert err.retryable is True
        assert err.retry_after == 30.0
        assert err.provider == "groq"

    def test_is_llm_provider_error(self) -> None:
        err = RateLimitError("limited")
        assert isinstance(err, LLMProviderError)


class TestContextLengthError:
    def test_basic(self) -> None:
        err = ContextLengthError("too long", provider="deepseek")
        assert err.retryable is False
        assert err.provider == "deepseek"

    def test_is_llm_provider_error(self) -> None:
        err = ContextLengthError("too long")
        assert isinstance(err, LLMProviderError)


class TestBaseLLMProvider:
    """Test BaseLLMProvider abstract interface (lines 67, 73, 91, 96)."""

    def test_concrete_implementation(self) -> None:
        from provenmesh.extraction.providers.base import BaseLLMProvider

        class TestProvider(BaseLLMProvider):
            @property
            def provider_name(self) -> str:
                return "test_provider"

            @property
            def model_name(self) -> str:
                return "test_model"

            async def generate(
                self,
                system_prompt: str,
                user_prompt: str,
                *,
                temperature: float = 0.0,
                max_tokens: int = 4096,
            ) -> LLMResponse:
                return LLMResponse(
                    content="response",
                    provider=self.provider_name,
                    model=self.model_name,
                )

            async def close(self) -> None:
                pass

        provider = TestProvider()
        assert provider.provider_name == "test_provider"
        assert provider.model_name == "test_model"

    def test_cannot_instantiate_abstract(self) -> None:
        from provenmesh.extraction.providers.base import BaseLLMProvider
        with pytest.raises(TypeError):
            BaseLLMProvider()  # type: ignore

