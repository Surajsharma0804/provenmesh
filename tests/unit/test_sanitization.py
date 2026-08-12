"""Unit tests for sanitization and normalization."""

from __future__ import annotations

from provenmesh.crawler.normalization import extract_domain, extract_owner_repo, normalize_url
from provenmesh.security.sanitization import sanitize_entity_name, sanitize_text, sanitize_url


class TestUrlSanitization:
    """Tests for URL sanitization."""

    def test_strips_tracking_params(self) -> None:
        url = "https://example.com/page?utm_source=google&important=yes"
        result = sanitize_url(url)
        assert "utm_source" not in result
        assert "important=yes" in result

    def test_strips_www(self) -> None:
        result = sanitize_url("https://www.example.com/page")
        assert "www." not in result

    def test_forces_https(self) -> None:
        result = sanitize_url("http://example.com/page")
        assert result.startswith("https://")

    def test_removes_trailing_slash(self) -> None:
        result = sanitize_url("https://example.com/page/")
        assert not result.endswith("/")


class TestUrlNormalization:
    """Tests for URL normalization."""

    def test_resolve_relative(self) -> None:
        result = normalize_url("/about", "https://example.com/page")
        assert result == "https://example.com/about"

    def test_extract_domain(self) -> None:
        assert extract_domain("https://www.example.com/page") == "example.com"

    def test_extract_github_repo(self) -> None:
        assert extract_owner_repo("https://github.com/openai/whisper") == "openai/whisper"
        assert extract_owner_repo("https://github.com/user/repo/tree/main") == "user/repo"


class TestTextSanitization:
    """Tests for text sanitization."""

    def test_decode_html_entities(self) -> None:
        result = sanitize_text("OpenAI &amp; Anthropic &lt;AI&gt;")
        assert "OpenAI & Anthropic <AI>" == result

    def test_collapse_whitespace(self) -> None:
        result = sanitize_text("Hello    World\t\tTest")
        assert result == "Hello World Test"

    def test_remove_null_bytes(self) -> None:
        result = sanitize_text("Hello\x00World")
        assert "\x00" not in result


class TestEntityNameSanitization:
    """Tests for entity name normalization."""

    def test_strips_legal_suffix(self) -> None:
        assert sanitize_entity_name("OpenAI Inc.") == "openai"
        assert sanitize_entity_name("Anthropic LLC") == "anthropic"
        assert sanitize_entity_name("DeepMind Ltd") == "deepmind"

    def test_lowercase(self) -> None:
        assert sanitize_entity_name("OpenAI") == "openai"

    def test_collapse_whitespace(self) -> None:
        assert sanitize_entity_name("Open  AI") == "open ai"

    def test_empty_string(self) -> None:
        assert sanitize_entity_name("") == ""
