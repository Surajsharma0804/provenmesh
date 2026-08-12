"""Transaction management — safe commit-then-ACK ordering (v2 §38).

A worker must never:
    DB write → crash → queue ACK

Instead:
    process message → DB transaction → commit → ACK queue

If DB transaction fails → no ACK → retry.
This provides at-least-once delivery with idempotent consumers.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession

from provenmesh.observability.logging import get_logger
from provenmesh.storage.database import get_session

logger = get_logger(__name__)


@asynccontextmanager
async def unit_of_work() -> AsyncGenerator[AsyncSession, None]:
    """Transactional unit of work — commit or rollback atomically.

    All database operations within this context are part of a single
    transaction. If any operation fails, everything rolls back.

    Usage:
        async with unit_of_work() as session:
            session.add(entity)
            session.add(edge)
            # Commit happens automatically on successful exit
        # ONLY after this block exits successfully should you ACK the queue
    """
    async with get_session() as session:
        async with session.begin():
            try:
                yield session
            except Exception:
                logger.error("transaction_rollback")
                raise
            # If we get here without exception, commit happens via session.begin()


@asynccontextmanager
async def read_only_session() -> AsyncGenerator[AsyncSession, None]:
    """Read-only session — no commit, no transaction overhead.

    Use for queries that don't modify data (export reads, health checks, etc.)
    """
    async with get_session() as session:
        yield session
