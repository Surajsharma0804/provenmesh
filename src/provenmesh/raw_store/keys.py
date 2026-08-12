"""S3 key generation — deterministic, content-addressed storage paths (v2 §9).

Pattern: raw/{source}/{YYYY}/{MM}/{DD}/{content_hash}/
Each raw payload stored as:
    payload.html
    metadata.json
    headers.json
"""

from __future__ import annotations

from datetime import UTC, datetime


def generate_raw_key(
    source_name: str,
    content_hash: str,
    extension: str = "html",
    timestamp: datetime | None = None,
) -> str:
    """Generate S3 key for a raw payload.

    Format: raw/{source}/{YYYY}/{MM}/{DD}/{content_hash}/payload.{ext}
    """
    ts = timestamp or datetime.now(UTC)
    return (
        f"raw/{source_name}/"
        f"{ts.strftime('%Y/%m/%d')}/"
        f"{content_hash}/"
        f"payload.{extension}"
    )


def generate_metadata_key(
    source_name: str,
    content_hash: str,
    timestamp: datetime | None = None,
) -> str:
    """Generate S3 key for payload metadata."""
    ts = timestamp or datetime.now(UTC)
    return (
        f"raw/{source_name}/"
        f"{ts.strftime('%Y/%m/%d')}/"
        f"{content_hash}/"
        f"metadata.json"
    )


def generate_headers_key(
    source_name: str,
    content_hash: str,
    timestamp: datetime | None = None,
) -> str:
    """Generate S3 key for response headers."""
    ts = timestamp or datetime.now(UTC)
    return (
        f"raw/{source_name}/"
        f"{ts.strftime('%Y/%m/%d')}/"
        f"{content_hash}/"
        f"headers.json"
    )


def extract_content_hash_from_key(s3_key: str) -> str:
    """Extract the content hash from an S3 key."""
    parts = s3_key.split("/")
    if len(parts) >= 6:
        return parts[-2]  # content_hash is second to last
    return ""
