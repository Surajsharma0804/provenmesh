"""S3-compatible object store client — immutable raw evidence archive (PDF §9).

Every successful fetch gets stored before extraction. This enables
re-extraction without re-scraping if the LLM schema changes.
"""

from __future__ import annotations

import json
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

import aiobotocore.session

from provenmesh.config.settings import get_settings
from provenmesh.domain.evidence import CrawlManifest
from provenmesh.observability.logging import get_logger
from provenmesh.raw_store.keys import (
    generate_headers_key,
    generate_metadata_key,
    generate_raw_key,
)

logger = get_logger(__name__)


@asynccontextmanager
async def _get_s3_client() -> AsyncGenerator[Any, None]:
    """Get an aiobotocore S3 client."""
    settings = get_settings()
    session = aiobotocore.session.get_session()
    async with session.create_client(
        "s3",
        endpoint_url=settings.s3_endpoint,
        aws_access_key_id=settings.s3_access_key,
        aws_secret_access_key=settings.s3_secret_key.get_secret_value(),
        region_name=settings.s3_region,
    ) as client:
        yield client


async def store_raw_payload(
    content: bytes,
    manifest: CrawlManifest,
) -> str:
    """Store raw fetched content + metadata in S3.

    Returns the S3 key for the stored payload.

    Three objects per fetch:
        1. payload.html — raw content
        2. metadata.json — crawl manifest
        3. headers.json — HTTP response headers
    """
    settings = get_settings()
    bucket = settings.s3_bucket

    # Determine extension from content type
    ext = "html"
    if "json" in manifest.content_type:
        ext = "json"
    elif "xml" in manifest.content_type:
        ext = "xml"
    elif "pdf" in manifest.content_type:
        ext = "pdf"

    payload_key = generate_raw_key(
        manifest.source_name, manifest.content_hash, ext,
    )
    metadata_key = generate_metadata_key(
        manifest.source_name, manifest.content_hash,
    )
    headers_key = generate_headers_key(
        manifest.source_name, manifest.content_hash,
    )

    async with _get_s3_client() as client:
        # 1. Store raw payload
        await client.put_object(
            Bucket=bucket,
            Key=payload_key,
            Body=content,
            ContentType=manifest.content_type,
        )

        # 2. Store metadata
        metadata_json = manifest.model_dump_json(indent=2)
        await client.put_object(
            Bucket=bucket,
            Key=metadata_key,
            Body=metadata_json.encode("utf-8"),
            ContentType="application/json",
        )

        # 3. Store response headers
        headers_json = json.dumps(manifest.headers, indent=2)
        await client.put_object(
            Bucket=bucket,
            Key=headers_key,
            Body=headers_json.encode("utf-8"),
            ContentType="application/json",
        )

    logger.info(
        "raw_payload_stored",
        s3_key=payload_key,
        content_hash=manifest.content_hash,
        content_length=len(content),
        source=manifest.source_name,
    )

    return payload_key


async def retrieve_raw_payload(s3_key: str) -> bytes:
    """Retrieve a raw payload from S3 by key."""
    settings = get_settings()
    async with _get_s3_client() as client:
        response = await client.get_object(Bucket=settings.s3_bucket, Key=s3_key)
        async with response["Body"] as stream:
            return await stream.read()


async def retrieve_manifest(
    source_name: str,
    content_hash: str,
) -> CrawlManifest | None:
    """Retrieve the crawl manifest for a stored payload."""
    settings = get_settings()
    metadata_key = generate_metadata_key(source_name, content_hash)

    try:
        async with _get_s3_client() as client:
            response = await client.get_object(
                Bucket=settings.s3_bucket, Key=metadata_key,
            )
            async with response["Body"] as stream:
                data = await stream.read()
                return CrawlManifest.model_validate_json(data)
    except Exception:
        return None
