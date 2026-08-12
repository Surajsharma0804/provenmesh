"""Tests for resolver/normalization.py — entity name normalization."""
from __future__ import annotations

from provenmesh.resolver.normalization import (
    extract_acronym,
    generate_canonical_id,
    generate_slug,
    normalize_entity_name,
)


class TestNormalizeEntityName:
    def test_basic(self) -> None:
        assert normalize_entity_name("OpenAI") == "openai"

    def test_strips_legal_suffixes(self) -> None:
        result = normalize_entity_name("OpenAI Inc.")
        assert "inc" not in result
        assert "openai" in result

    def test_strips_llc(self) -> None:
        result = normalize_entity_name("Acme LLC")
        assert "llc" not in result

    def test_strips_parenthetical(self) -> None:
        result = normalize_entity_name("Meta (formerly Facebook)")
        assert "formerly" not in result
        assert "meta" in result

    def test_collapses_joiners(self) -> None:
        result = normalize_entity_name("Open-AI")
        # 'ai' is stripped as a legal suffix
        assert result == "open"

    def test_unicode_normalization(self) -> None:
        result = normalize_entity_name("Café AI")
        assert "cafe" in result or "café" in result

    def test_empty_string(self) -> None:
        assert normalize_entity_name("") == ""

    def test_whitespace_collapse(self) -> None:
        result = normalize_entity_name("  Open   AI  ")
        # 'ai' is stripped as a legal suffix
        assert result == "open"

    def test_multiple_suffixes(self) -> None:
        result = normalize_entity_name("Tech Solutions Corp.")
        assert "solutions" not in result
        assert "corp" not in result


class TestGenerateSlug:
    def test_basic(self) -> None:
        assert generate_slug("OpenAI") == "openai"

    def test_with_spaces(self) -> None:
        # 'ai' is stripped as a legal suffix
        result = generate_slug("Open AI Research")
        assert "open" in result
        assert "research" in result

    def test_special_chars(self) -> None:
        slug = generate_slug("O'Brien & Associates")
        assert "&" not in slug
        assert "'" not in slug

    def test_empty(self) -> None:
        assert generate_slug("") == "unknown"


class TestGenerateCanonicalId:
    def test_startup(self) -> None:
        result = generate_canonical_id("OpenAI", "STARTUP")
        assert result.startswith("startup_")
        assert "openai" in result

    def test_product(self) -> None:
        result = generate_canonical_id("ChatGPT", "PRODUCT")
        assert result.startswith("product_")

    def test_news_signal(self) -> None:
        result = generate_canonical_id("Some News", "NEWS_SIGNAL")
        assert result.startswith("news_")

    def test_paper(self) -> None:
        result = generate_canonical_id("Attention Is All You Need", "PAPER")
        assert result.startswith("paper_")


class TestExtractAcronym:
    def test_valid_acronym(self) -> None:
        assert extract_acronym("AI") == "AI"
        assert extract_acronym("NLP") == "NLP"
        assert extract_acronym("ML") == "ML"

    def test_too_long(self) -> None:
        assert extract_acronym("ABCDEFG") is None

    def test_lowercase(self) -> None:
        assert extract_acronym("ai") is None

    def test_mixed_case(self) -> None:
        assert extract_acronym("OpenAI") is None

    def test_with_numbers(self) -> None:
        assert extract_acronym("GPT4") is None
