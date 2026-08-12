"""Tests for crawler/dedup.py — dedup hash computation (pure functions only)."""
from __future__ import annotations

from provenmesh.crawler.dedup import compute_content_hash, compute_dedup_hash


class TestComputeDedupHash:
    def test_same_input_same_hash(self) -> None:
        h1 = compute_dedup_hash("https://example.com", "Title", "source")
        h2 = compute_dedup_hash("https://example.com", "Title", "source")
        assert h1 == h2

    def test_different_url_different_hash(self) -> None:
        h1 = compute_dedup_hash("https://example.com/a", "Title", "src")
        h2 = compute_dedup_hash("https://example.com/b", "Title", "src")
        assert h1 != h2

    def test_different_title_different_hash(self) -> None:
        h1 = compute_dedup_hash("https://example.com", "Title A", "src")
        h2 = compute_dedup_hash("https://example.com", "Title B", "src")
        assert h1 != h2

    def test_hash_is_hex(self) -> None:
        h = compute_dedup_hash("https://example.com")
        assert len(h) == 64  # SHA-256 hex
        assert all(c in "0123456789abcdef" for c in h)

    def test_empty_title_and_source(self) -> None:
        h = compute_dedup_hash("https://example.com")
        assert len(h) == 64


class TestComputeContentHash:
    def test_bytes_input(self) -> None:
        h = compute_content_hash(b"hello world")
        assert len(h) == 64

    def test_string_input(self) -> None:
        h = compute_content_hash("hello world")
        assert len(h) == 64

    def test_same_content_same_hash(self) -> None:
        h1 = compute_content_hash("test content")
        h2 = compute_content_hash("test content")
        assert h1 == h2

    def test_different_content_different_hash(self) -> None:
        h1 = compute_content_hash("content A")
        h2 = compute_content_hash("content B")
        assert h1 != h2

    def test_bytes_and_string_same(self) -> None:
        h1 = compute_content_hash(b"hello")
        h2 = compute_content_hash("hello")
        assert h1 == h2
