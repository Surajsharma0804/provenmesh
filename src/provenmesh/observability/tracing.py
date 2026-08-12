"""Distributed tracing support — correlation ID propagation across workers."""

from __future__ import annotations

import uuid
from contextlib import contextmanager
from typing import Generator

from provenmesh.observability.logging import (
    get_correlation_id,
    get_logger,
    set_correlation_id,
)

logger = get_logger(__name__)


@contextmanager
def trace_operation(
    operation: str,
    *,
    correlation_id: str | None = None,
    **extra: str | int | float,
) -> Generator[str, None, None]:
    """Context manager that sets a correlation ID and logs operation boundaries.

    Usage:
        with trace_operation("fetch_page", url=url) as cid:
            result = await fetch(url)
    """
    previous_cid = get_correlation_id()
    cid = correlation_id or previous_cid or str(uuid.uuid4())
    set_correlation_id(cid)

    logger.info(
        f"{operation}_started",
        operation=operation,
        correlation_id=cid,
        **extra,
    )

    try:
        yield cid
    except Exception as exc:
        logger.error(
            f"{operation}_failed",
            operation=operation,
            correlation_id=cid,
            error=str(exc),
            error_type=type(exc).__name__,
            **extra,
        )
        raise
    else:
        logger.info(
            f"{operation}_completed",
            operation=operation,
            correlation_id=cid,
            **extra,
        )
    finally:
        # Restore previous correlation ID if we changed it
        if previous_cid and previous_cid != cid:
            set_correlation_id(previous_cid)


def create_span_id() -> str:
    """Create a unique span ID for sub-operations within a trace."""
    return uuid.uuid4().hex[:16]
