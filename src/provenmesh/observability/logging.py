"""Structured JSON logging with correlation IDs (PDF §10.1).

Every log line is JSON with a correlation_id tying a raw fetch to its
LLM extraction and resolution outcome, so a single record's full
lifecycle can be traced.
"""

from __future__ import annotations

import json
import logging
import logging.config
import sys
import uuid
from contextvars import ContextVar
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import structlog
import yaml

# Context variable for correlation ID propagation across async calls
_correlation_id: ContextVar[str] = ContextVar("correlation_id", default="")


def get_correlation_id() -> str:
    """Get current correlation ID or generate a new one."""
    cid = _correlation_id.get()
    if not cid:
        cid = str(uuid.uuid4())
        _correlation_id.set(cid)
    return cid


def set_correlation_id(cid: str) -> None:
    """Set the correlation ID for the current async context."""
    _correlation_id.set(cid)


def new_correlation_id() -> str:
    """Generate and set a new correlation ID."""
    cid = str(uuid.uuid4())
    _correlation_id.set(cid)
    return cid


class JSONFormatter(logging.Formatter):
    """JSON log formatter that includes correlation_id in every line (PDF §10.1)."""

    def format(self, record: logging.LogRecord) -> str:
        log_entry: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "correlation_id": get_correlation_id(),
        }

        # Add extra fields from structlog or manual binding
        if hasattr(record, "event"):
            log_entry["event"] = record.event  # type: ignore[attr-defined]

        # Include exception info if present
        if record.exc_info and record.exc_info[1]:
            log_entry["exception"] = {
                "type": type(record.exc_info[1]).__name__,
                "message": str(record.exc_info[1]),
            }

        # Merge any extra attributes
        for key in ("item_id", "url", "source_name", "provider", "latency_ms",
                     "tokens", "stage", "worker_id", "fetch_tier", "cost_usd"):
            if hasattr(record, key):
                log_entry[key] = getattr(record, key)

        return json.dumps(log_entry, default=str)


def add_correlation_id(
    logger: Any, method_name: str, event_dict: dict[str, Any],
) -> dict[str, Any]:
    """Structlog processor that adds correlation_id to every log entry."""
    event_dict["correlation_id"] = get_correlation_id()
    return event_dict


def add_service_info(
    logger: Any, method_name: str, event_dict: dict[str, Any],
) -> dict[str, Any]:
    """Structlog processor that adds service metadata."""
    if "service" not in event_dict:
        event_dict["service"] = "provenmesh"
    return event_dict


def setup_logging(config_path: Path | None = None) -> None:
    """Initialize logging from YAML config + structlog processors.

    Falls back to a sensible default if no config file is provided.
    """
    # Ensure logs directory exists
    logs_dir = Path("logs")
    logs_dir.mkdir(exist_ok=True)

    if config_path and config_path.exists():
        with open(config_path) as f:
            config = yaml.safe_load(f)
        logging.config.dictConfig(config)
    else:
        # Default configuration
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            stream=sys.stdout,
        )

    # Configure structlog for async-safe, JSON-compatible logging
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            add_correlation_id,
            add_service_info,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            structlog.processors.JSONRenderer(),
        ],
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """Get a named structlog logger with correlation ID support."""
    return structlog.get_logger(name)
