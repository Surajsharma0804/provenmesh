"""Async SQLAlchemy database engine and session management.

Uses PostgreSQL + pgvector as the primary datastore (PDF §9).
All database access goes through async sessions for non-blocking I/O.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from provenmesh.config.settings import get_settings
from provenmesh.observability.logging import get_logger

logger = get_logger(__name__)

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


async def get_engine() -> AsyncEngine:
    """Get or create the async SQLAlchemy engine."""
    global _engine  # noqa: PLW0603
    if _engine is None:
        settings = get_settings()
        _engine = create_async_engine(
            settings.postgres_dsn,
            echo=settings.debug,
            pool_size=10,
            max_overflow=20,
            pool_pre_ping=True,
            pool_recycle=3600,
            connect_args={
                "server_settings": {
                    "application_name": "provenmesh",
                    "jit": "off",
                },
            },
        )
        logger.info("database_engine_created")
    return _engine


async def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Get or create the async session factory."""
    global _session_factory  # noqa: PLW0603
    if _session_factory is None:
        engine = await get_engine()
        _session_factory = async_sessionmaker(
            engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )
    return _session_factory


@asynccontextmanager
async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Get an async database session.

    Usage:
        async with get_session() as session:
            result = await session.execute(query)
            session.add(entity)
            await session.commit()
    """
    factory = await get_session_factory()
    async with factory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise


async def close_database() -> None:
    """Dispose of the engine and all connections."""
    global _engine, _session_factory  # noqa: PLW0603
    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _session_factory = None
        logger.info("database_engine_disposed")
