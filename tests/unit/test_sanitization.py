"""Tests for security/sanitization.py — URL and text sanitization."""
from __future__ import annotations

from provenmesh.security.sanitization import (
    sanitize_entity_name,
    sanitize_text,
    sanitize_url,
)


class TestSanitizeUrl:
    def test_basic(self) -> None:
        result = sanitize_url("https://example.com/page")
        assert "example.com" in result

    def test_empty(self) -> None:
        assert sanitize_url("") == ""

    def test_strips_tracking(self) -> None:
        result = sanitize_url("https://example.com/page?id=1&utm_source=google")
        assert "utm_source" not in result
        assert "id=1" in result

    def test_forces_https(self) -> None:
        result = sanitize_url("http://example.com/page")
        assert result.startswith("https://")

    def test_strips_www(self) -> None:
        result = sanitize_url("https://www.example.com")
        assert "www." not in result

    def test_removes_trailing_slash(self) -> None:
        result = sanitize_url("https://example.com/page/")
        assert not result.endswith("/")

    def test_strips_fragment(self) -> None:
        result = sanitize_url("https://example.com/page#section")
        assert "#" not in result


class TestSanitizeText:
    def test_basic(self) -> None:
        assert sanitize_text("hello world") == "hello world"

    def test_empty(self) -> None:
        assert sanitize_text("") == ""

    def test_html_entities(self) -> None:
        result = sanitize_text("AT&amp;T &amp; Friends")
        assert "AT&T" in result

    def test_control_chars(self) -> None:
        result = sanitize_text("hello\x00world\x01test")
        assert "\x00" not in result
        assert "helloworld" in result

    def test_whitespace_collapse(self) -> None:
        result = sanitize_text("hello   world")
        assert result == "hello world"

    def test_newline_collapse(self) -> None:
        result = sanitize_text("hello\n\n\n\nworld")
        assert result == "hello\n\nworld"


class TestSanitizeEntityName:
    def test_basic(self) -> None:
        assert sanitize_entity_name("OpenAI") == "openai"

    def test_empty(self) -> None:
        assert sanitize_entity_name("") == ""

    def test_strips_inc(self) -> None:
        result = sanitize_entity_name("OpenAI Inc.")
        assert "inc" not in result

    def test_strips_ltd(self) -> None:
        result = sanitize_entity_name("Company Ltd")
        assert "ltd" not in result

    def test_strips_llc(self) -> None:
        result = sanitize_entity_name("Company LLC")
        assert "llc" not in result

    def test_strips_corp(self) -> None:
        result = sanitize_entity_name("Company Corp.")
        assert "corp" not in result

    def test_collapses_whitespace(self) -> None:
        result = sanitize_entity_name("  Open  AI  ")
        assert result == "open ai"

    def test_strips_edge_punctuation(self) -> None:
        result = sanitize_entity_name("...OpenAI...")
        assert result == "openai"
