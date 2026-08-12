"""Unit tests for deduplication — hash computation and uniqueness guarantees."""

from __future__ import annotations

import pytest

from provenmesh.crawler.dedup import compute_content_hash, compute_dedup_hash


class TestDedupHash:
    """Tests for dedup fingerprint computation."""

    def test_deterministic_hash(self) -> None:
        """Same inputs always produce the same hash."""
        h1 = compute_dedup_hash("https://example.com/page", "Test Title", "source1")
        h2 = compute_dedup_hash("https://example.com/page", "Test Title", "source1")
        assert h1 == h2

    def test_different_urls_different_hash(self) -> None:
        h1 = compute_dedup_hash("https://example.com/page1", "Title", "source1")
        h2 = compute_dedup_hash("https://example.com/page2", "Title", "source1")
        assert h1 != h2

    def test_url_normalization(self) -> None:
        """URLs are normalized before hashing."""
        h1 = compute_dedup_hash("https://example.com/page?utm_source=x", "Title", "src")
        h2 = compute_dedup_hash("https://example.com/page", "Title", "src")
        assert h1 == h2  # utm params stripped

    def test_title_normalization(self) -> None:
        """Titles are normalized (lowercase, collapsed whitespace)."""
        h1 = compute_dedup_hash("https://example.com", "Test  Title", "src")
        h2 = compute_dedup_hash("https://example.com", "test title", "src")
        assert h1 == h2

    def test_empty_inputs(self) -> None:
        """Empty inputs produce a valid hash."""
        h = compute_dedup_hash("", "", "")
        assert len(h) == 64  # SHA-256 hex length


class TestContentHash:
    """Tests for content-level hashing."""

    def test_bytes_hash(self) -> None:
        h = compute_content_hash(b"<html>test content</html>")
        assert len(h) == 64

    def test_string_hash(self) -> None:
        h = compute_content_hash("<html>test content</html>")
        assert len(h) == 64

    def test_same_content_same_hash(self) -> None:
        h1 = compute_content_hash(b"content")
        h2 = compute_content_hash(b"content")
        assert h1 == h2

    def test_different_content_different_hash(self) -> None:
        h1 = compute_content_hash(b"content_a")
        h2 = compute_content_hash(b"content_b")
        assert h1 != h2
