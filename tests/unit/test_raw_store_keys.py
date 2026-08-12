"""Tests for raw_store/keys.py — S3 key generation."""
from __future__ import annotations

from datetime import UTC, datetime

from provenmesh.raw_store.keys import (
    extract_content_hash_from_key,
    generate_headers_key,
    generate_metadata_key,
    generate_raw_key,
)


class TestGenerateRawKey:
    def test_basic(self) -> None:
        ts = datetime(2026, 8, 12, tzinfo=UTC)
        key = generate_raw_key("crunchbase", "abc123", timestamp=ts)
        assert key == "raw/crunchbase/2026/08/12/abc123/payload.html"

    def test_custom_extension(self) -> None:
        ts = datetime(2026, 1, 1, tzinfo=UTC)
        key = generate_raw_key("arxiv", "hash1", extension="xml", timestamp=ts)
        assert key.endswith("payload.xml")

    def test_default_extension(self) -> None:
        key = generate_raw_key("src", "h1")
        assert "payload.html" in key

    def test_auto_timestamp(self) -> None:
        key = generate_raw_key("src", "h1")
        assert key.startswith("raw/src/")


class TestGenerateMetadataKey:
    def test_basic(self) -> None:
        ts = datetime(2026, 8, 12, tzinfo=UTC)
        key = generate_metadata_key("crunchbase", "abc123", timestamp=ts)
        assert key == "raw/crunchbase/2026/08/12/abc123/metadata.json"


class TestGenerateHeadersKey:
    def test_basic(self) -> None:
        ts = datetime(2026, 8, 12, tzinfo=UTC)
        key = generate_headers_key("crunchbase", "abc123", timestamp=ts)
        assert key == "raw/crunchbase/2026/08/12/abc123/headers.json"


class TestExtractContentHash:
    def test_valid_key(self) -> None:
        key = "raw/crunchbase/2026/08/12/abc123/payload.html"
        assert extract_content_hash_from_key(key) == "abc123"

    def test_short_key(self) -> None:
        assert extract_content_hash_from_key("short/key") == ""

    def test_empty_key(self) -> None:
        assert extract_content_hash_from_key("") == ""
