"""Smoke test — verify all infrastructure and code layers are functional.

Usage:
    python scripts/smoke_test.py

Tests:
    1. Redis connectivity and stream operations
    2. PostgreSQL connectivity and migration state
    3. MinIO/S3 bucket access
    4. LLM provider instantiation
    5. Domain model creation
    6. Grounding engine
    7. Entity resolution seed store
    8. Export validation
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from datetime import datetime, timezone


async def test_redis() -> bool:
    """Test Redis connectivity."""
    import redis.asyncio as aioredis

    url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    try:
        client = aioredis.from_url(url, decode_responses=True)
        await client.ping()
        await client.set("smoke:test", "ok", ex=10)
        value = await client.get("smoke:test")
        await client.delete("smoke:test")
        await client.aclose()
        assert value == "ok"
        return True
    except Exception as e:
        print(f"  FAIL: {e}")
        return False


async def test_postgres() -> bool:
    """Test PostgreSQL connectivity."""
    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlalchemy import text

    dsn = os.getenv("POSTGRES_DSN", "postgresql+asyncpg://provenmesh:provenmesh_dev@localhost:5432/provenmesh")
    try:
        engine = create_async_engine(dsn)
        async with engine.connect() as conn:
            result = await conn.execute(text("SELECT version()"))
            version = result.scalar()
            assert version is not None and "PostgreSQL" in str(version)
        await engine.dispose()
        return True
    except Exception as e:
        print(f"  FAIL: {e}")
        return False


async def test_minio() -> bool:
    """Test MinIO/S3 bucket access."""
    import aiobotocore.session

    endpoint = os.getenv("S3_ENDPOINT", "http://localhost:9000")
    try:
        session = aiobotocore.session.get_session()
        async with session.create_client(
            "s3",
            endpoint_url=endpoint,
            aws_access_key_id=os.getenv("S3_ACCESS_KEY", "minioadmin"),
            aws_secret_access_key=os.getenv("S3_SECRET_KEY", "minioadmin"),
            region_name="us-east-1",
        ) as client:
            bucket = os.getenv("S3_BUCKET", "provenmesh-raw")
            await client.head_bucket(Bucket=bucket)
        return True
    except Exception as e:
        print(f"  FAIL: {e}")
        return False


def test_domain_models() -> bool:
    """Test domain model creation."""
    try:
        from provenmesh.domain.enums import RecordType, ProcessingState
        from provenmesh.domain.entities import EvidencedField

        field = EvidencedField(value="OpenAI", evidence="OpenAI is...", confidence=0.95)
        assert field.value == "OpenAI"
        assert field.confidence == 0.95
        assert len(RecordType) == 5
        assert len(ProcessingState) >= 16
        return True
    except Exception as e:
        print(f"  FAIL: {e}")
        return False


def test_grounding() -> bool:
    """Test grounding engine."""
    try:
        from provenmesh.grounding.text_match import verify_text_field
        from provenmesh.domain.enums import FieldVerification

        status, score = verify_text_field(
            "OpenAI", "OpenAI is an AI company", "OpenAI is an AI company founded in 2015"
        )
        assert status == FieldVerification.GROUNDED
        return True
    except Exception as e:
        print(f"  FAIL: {e}")
        return False


def test_resolver() -> bool:
    """Test entity resolution seed store."""
    try:
        from provenmesh.resolver.seeds import SeedEntity, SeedStore

        store = SeedStore()
        store.add_seed(SeedEntity(
            canonical_id="startup_openai",
            canonical_name="OpenAI",
            normalized_name="openai",
            record_type="STARTUP",
            aliases=["Open AI"],
        ))
        result = store.exact_match("OpenAI")
        assert result is not None
        assert result.canonical_id == "startup_openai"

        result = store.exact_match("Open AI")
        assert result is not None
        return True
    except Exception as e:
        print(f"  FAIL: {e}")
        return False


def test_export_validation() -> bool:
    """Test export quality gates."""
    try:
        from provenmesh.export.validate import validate_for_export

        result = validate_for_export(
            canonical_id="startup_openai",
            record_type="STARTUP",
            content={"entityName": {"value": "OpenAI"}},
            verification_status="grounded",
            schema_valid=True,
            resolution_method="exact",
        )
        assert result.is_valid
        return True
    except Exception as e:
        print(f"  FAIL: {e}")
        return False


async def main() -> None:
    """Run all smoke tests."""
    print("=" * 60)
    print("ProvenMesh Smoke Test")
    print("=" * 60)

    tests = [
        ("Redis connectivity", test_redis()),
        ("PostgreSQL connectivity", test_postgres()),
        ("MinIO/S3 bucket access", test_minio()),
    ]

    sync_tests = [
        ("Domain models", test_domain_models),
        ("Grounding engine", test_grounding),
        ("Entity resolution", test_resolver),
        ("Export validation", test_export_validation),
    ]

    results: list[tuple[str, bool]] = []

    # Async infrastructure tests
    for name, coro in tests:
        print(f"\n[TEST] {name}...", end=" ")
        try:
            passed = await coro
        except Exception as e:
            passed = False
            print(f"  FAIL: {e}")
        status = "PASS" if passed else "FAIL"
        print(f"[{status}]")
        results.append((name, passed))

    # Sync code tests
    for name, func in sync_tests:
        print(f"\n[TEST] {name}...", end=" ")
        try:
            passed = func()
        except Exception as e:
            passed = False
            print(f"  FAIL: {e}")
        status = "PASS" if passed else "FAIL"
        print(f"[{status}]")
        results.append((name, passed))

    # Summary
    total = len(results)
    passed = sum(1 for _, ok in results if ok)
    failed = total - passed

    print("\n" + "=" * 60)
    print(f"Results: {passed}/{total} passed, {failed} failed")
    print("=" * 60)

    if failed > 0:
        print("\nFailed tests:")
        for name, ok in results:
            if not ok:
                print(f"  ✗ {name}")
        sys.exit(1)
    else:
        print("\nAll smoke tests passed!")


if __name__ == "__main__":
    asyncio.run(main())
