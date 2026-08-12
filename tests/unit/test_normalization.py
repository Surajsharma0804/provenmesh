"""Tests for crawler/normalization.py — URL and text normalization."""
from __future__ import annotations

from provenmesh.crawler.normalization import (
    extract_domain,
    extract_owner_repo,
    normalize_url,
    normalize_whitespace,
)


class TestNormalizeUrl:
    def test_basic_url(self) -> None:
        result = normalize_url("https://example.com/page")
        assert result == "https://example.com/page"

    def test_strips_www(self) -> None:
        result = normalize_url("https://www.example.com/page")
        assert "www." not in result

    def test_removes_fragment(self) -> None:
        result = normalize_url("https://example.com/page#section")
        assert "#section" not in result

    def test_removes_trailing_slash(self) -> None:
        result = normalize_url("https://example.com/page/")
        assert result.endswith("/page")

    def test_keeps_root_slash(self) -> None:
        result = normalize_url("https://example.com/")
        assert result.endswith("/")

    def test_removes_tracking_params(self) -> None:
        result = normalize_url(
            "https://example.com/page?id=1&utm_source=google&utm_medium=cpc",
        )
        assert "utm_source" not in result
        assert "utm_medium" not in result
        assert "id=1" in result

    def test_sorts_query_params(self) -> None:
        result = normalize_url("https://example.com/page?b=2&a=1")
        assert result.endswith("a=1&b=2")

    def test_relative_url(self) -> None:
        result = normalize_url(
            "/about", base_url="https://example.com",
        )
        assert "example.com/about" in result

    def test_empty_url(self) -> None:
        assert normalize_url("") == ""

    def test_lowercase(self) -> None:
        result = normalize_url("HTTPS://EXAMPLE.COM/Page")
        assert "https://" in result
        assert "example.com" in result


class TestExtractDomain:
    def test_basic(self) -> None:
        assert extract_domain("https://example.com/page") == "example.com"

    def test_strips_www(self) -> None:
        assert extract_domain("https://www.example.com") == "example.com"

    def test_with_port(self) -> None:
        result = extract_domain("https://example.com:8080/page")
        assert "example.com" in result


class TestNormalizeWhitespace:
    def test_collapses_spaces(self) -> None:
        assert normalize_whitespace("hello   world") == "hello world"

    def test_strips_edges(self) -> None:
        assert normalize_whitespace("  hello  ") == "hello"

    def test_newlines(self) -> None:
        assert normalize_whitespace("hello\n\nworld") == "hello world"


class TestExtractOwnerRepo:
    def test_github_url(self) -> None:
        assert extract_owner_repo(
            "https://github.com/openai/whisper",
        ) == "openai/whisper"

    def test_github_url_with_path(self) -> None:
        result = extract_owner_repo(
            "https://github.com/facebook/react/tree/main",
        )
        assert result == "facebook/react"

    def test_short_path(self) -> None:
        assert extract_owner_repo("https://github.com/openai") == ""

    def test_empty(self) -> None:
        assert extract_owner_repo("") == ""
