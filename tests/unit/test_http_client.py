"""Tests for crawler/http_client.py — FetchResult class and properties."""
from __future__ import annotations

from provenmesh.crawler.http_client import FetchResult


class TestFetchResult:
    def test_ok_success(self) -> None:
        r = FetchResult(url="https://example.com", status=200)
        assert r.ok is True

    def test_ok_redirect(self) -> None:
        r = FetchResult(url="https://example.com", status=301)
        assert r.ok is True

    def test_ok_error_status(self) -> None:
        r = FetchResult(url="https://example.com", status=404)
        assert r.ok is False

    def test_ok_with_error_string(self) -> None:
        r = FetchResult(url="https://example.com", status=200, error="timeout")
        assert r.ok is False

    def test_text_utf8(self) -> None:
        r = FetchResult(url="u", content=b"hello world", encoding="utf-8")
        assert r.text == "hello world"

    def test_text_fallback_encoding(self) -> None:
        r = FetchResult(url="u", content=b"\xff\xfe", encoding="invalid-codec")
        text = r.text
        assert isinstance(text, str)

    def test_text_latin1_fallback(self) -> None:
        r = FetchResult(url="u", content=b"\x80\x81", encoding="utf-8")
        text = r.text
        assert isinstance(text, str)

    def test_is_rate_limited(self) -> None:
        r = FetchResult(url="u", status=429)
        assert r.is_rate_limited is True
        r2 = FetchResult(url="u", status=200)
        assert r2.is_rate_limited is False

    def test_is_server_error(self) -> None:
        r = FetchResult(url="u", status=500)
        assert r.is_server_error is True
        r2 = FetchResult(url="u", status=502)
        assert r2.is_server_error is True
        r3 = FetchResult(url="u", status=404)
        assert r3.is_server_error is False

    def test_defaults(self) -> None:
        r = FetchResult(url="https://test.com")
        assert r.status == 0
        assert r.content == b""
        assert r.content_type == ""
        assert r.encoding == "utf-8"
        assert r.headers == {}
        assert r.elapsed_ms == 0
        assert r.fetch_tier == 1
        assert r.error == ""

    def test_custom_headers(self) -> None:
        r = FetchResult(url="u", headers={"X-Test": "val"})
        assert r.headers["X-Test"] == "val"
