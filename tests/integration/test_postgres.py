"""Integration tests — PostgreSQL with pgvector (v2 §41).

Requires a running PostgreSQL instance with pgvector extension.
Mark: @pytest.mark.integration
"""

from __future__ import annotations

import os
import uuid

import pytest

POSTGRES_DSN = os.getenv(
    "POSTGRES_DSN",
    "postgresql+asyncpg://provenmesh:provenmesh_dev@localhost:5432/provenmesh",
)


@pytest.fixture
async def db_session():
    """Provide a test database session with rollback."""
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    from sqlalchemy.orm import sessionmaker

    engine = create_async_engine(POSTGRES_DSN, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    try:
        async with engine.connect() as conn:
            await conn.execute("SELECT 1")  # type: ignore[arg-type]
    except Exception:
        pytest.skip("PostgreSQL not available")

    async with async_session() as session, session.begin():
        yield session
        await session.rollback()

    await engine.dispose()


@pytest.mark.integration
class TestEntityCRUD:
    """Test entity CRUD operations against real PostgreSQL."""

    async def test_insert_and_retrieve_entity(self, db_session):
        """Verify basic entity insert and retrieval."""
        from sqlalchemy import text

        canonical_id = f"test_startup_{uuid.uuid4().hex[:8]}"

        await db_session.execute(
            text("""
                INSERT INTO entities (canonical_id, record_type, entity_name, normalized_name,
                    content, resolution_method, resolution_confidence, is_seed,
                    verification_status, schema_valid)
                VALUES (:cid, :rt, :name, :nn, :content, :rm, :rc, :seed, :vs, :sv)
                ON CONFLICT (canonical_id) DO NOTHING
            """),
            {
                "cid": canonical_id,
                "rt": "STARTUP",
                "name": "Test Corp",
                "nn": "test corp",
                "content": '{"entityName": {"value": "Test Corp"}}',
                "rm": "exact",
                "rc": 1.0,
                "seed": False,
                "vs": "grounded",
                "sv": True,
            },
        )

        result = await db_session.execute(
            text("SELECT entity_name FROM entities WHERE canonical_id = :cid"),
            {"cid": canonical_id},
        )
        row = result.fetchone()
        assert row is not None
        assert row[0] == "Test Corp"

    async def test_upsert_idempotency(self, db_session):
        """Verify upsert does not create duplicates."""
        from sqlalchemy import text

        canonical_id = f"test_upsert_{uuid.uuid4().hex[:8]}"

        for attempt in range(3):
            await db_session.execute(
                text("""
                    INSERT INTO entities (canonical_id, record_type, entity_name, normalized_name,
                        content, resolution_method, resolution_confidence, is_seed,
                        verification_status, schema_valid, source_count)
                    VALUES (:cid, 'STARTUP', 'Upsert Test', 'upsert test',
                        '{}', 'exact', 1.0, false, 'grounded', true, :sc)
                    ON CONFLICT (canonical_id) DO UPDATE SET source_count = :sc
                """),
                {"cid": canonical_id, "sc": attempt + 1},
            )

        result = await db_session.execute(
            text("SELECT source_count FROM entities WHERE canonical_id = :cid"),
            {"cid": canonical_id},
        )
        row = result.fetchone()
        assert row is not None
        assert row[0] == 3


@pytest.mark.integration
class TestRelationshipEdges:
    """Test relationship edge operations."""

    async def test_relationship_unique_constraint(self, db_session):
        """Verify UNIQUE(source, target, type, url) prevents duplicates."""
        from sqlalchemy import text

        source_id = f"s_{uuid.uuid4().hex[:8]}"
        target_id = f"t_{uuid.uuid4().hex[:8]}"

        for _ in range(2):
            await db_session.execute(
                text("""
                    INSERT INTO relationships (source_id, target_id, relation_type,
                        confidence, source_url)
                    VALUES (:s, :t, 'BUILDS_PRODUCT', 0.95, 'https://example.com')
                    ON CONFLICT (source_id, target_id, relation_type, source_url) DO NOTHING
                """),
                {"s": source_id, "t": target_id},
            )

        result = await db_session.execute(
            text("SELECT COUNT(*) FROM relationships WHERE source_id = :s AND target_id = :t"),
            {"s": source_id, "t": target_id},
        )
        count = result.scalar()
        assert count == 1


@pytest.mark.integration
class TestPgvector:
    """Test pgvector extension for embedding similarity."""

    async def test_pgvector_extension_available(self, db_session):
        """Verify pgvector extension is installed."""
        from sqlalchemy import text

        result = await db_session.execute(
            text("SELECT extname FROM pg_extension WHERE extname = 'vector'")
        )
        row = result.fetchone()
        assert row is not None, "pgvector extension not installed"
