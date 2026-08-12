"""Contract tests — verify all LLM providers implement the same interface.

These tests run the same assertions against every provider in the
fallback chain (PDF §5.1 contract testing).
"""

from __future__ import annotations

import pytest

from provenmesh.extraction.providers.base import BaseLLMProvider
from provenmesh.extraction.providers.gemini import GeminiProvider
from provenmesh.extraction.providers.groq import GroqProvider
from provenmesh.extraction.providers.deepseek import DeepSeekProvider


ALL_PROVIDERS = [GeminiProvider, GroqProvider, DeepSeekProvider]


class TestProviderContract:
    """All providers must implement the BaseLLMProvider interface."""

    @pytest.mark.parametrize("provider_cls", ALL_PROVIDERS)
    def test_implements_base(self, provider_cls: type) -> None:
        assert issubclass(provider_cls, BaseLLMProvider)

    @pytest.mark.parametrize("provider_cls", ALL_PROVIDERS)
    def test_has_provider_name(self, provider_cls: type) -> None:
        provider = provider_cls()
        assert isinstance(provider.provider_name, str)
        assert len(provider.provider_name) > 0

    @pytest.mark.parametrize("provider_cls", ALL_PROVIDERS)
    def test_has_model_name(self, provider_cls: type) -> None:
        provider = provider_cls()
        assert isinstance(provider.model_name, str)
        assert len(provider.model_name) > 0

    @pytest.mark.parametrize("provider_cls", ALL_PROVIDERS)
    def test_unique_provider_names(self, provider_cls: type) -> None:
        names = [cls().provider_name for cls in ALL_PROVIDERS]
        assert len(set(names)) == len(names), "Provider names must be unique"

    @pytest.mark.parametrize("provider_cls", ALL_PROVIDERS)
    def test_has_generate_method(self, provider_cls: type) -> None:
        provider = provider_cls()
        assert hasattr(provider, "generate")
        assert callable(provider.generate)

    @pytest.mark.parametrize("provider_cls", ALL_PROVIDERS)
    def test_has_close_method(self, provider_cls: type) -> None:
        provider = provider_cls()
        assert hasattr(provider, "close")
        assert callable(provider.close)
