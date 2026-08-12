"""Date parsing engine — layered date extraction (PDF §4.1, §4.2).

Three priority levels:
    1. Structured metadata (<meta property=article:published_time>, JSON-LD)
    2. Explicit date strings via dateutil + dateparser with locale hints
    3. Relative expressions ("2 hours ago", "yesterday") resolved against fetch time

Every parsed date carries a confidence flag: strict or heuristic.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import NamedTuple

import dateparser
from dateutil import parser as dateutil_parser

from provenmesh.domain.enums import DateConfidence
from provenmesh.observability.logging import get_logger

logger = get_logger(__name__)


class ParsedDate(NamedTuple):
    """Result of date parsing with provenance."""

    value: datetime
    confidence: DateConfidence
    source: str  # e.g., "json_ld", "meta_tag", "dateutil", "relative", "heuristic"
    raw: str  # The original date string


# Relative date patterns
_RELATIVE_PATTERNS = [
    (re.compile(r"(\d+)\s*seconds?\s*ago", re.I), "seconds"),
    (re.compile(r"(\d+)\s*minutes?\s*ago", re.I), "minutes"),
    (re.compile(r"(\d+)\s*hours?\s*ago", re.I), "hours"),
    (re.compile(r"(\d+)\s*days?\s*ago", re.I), "days"),
    (re.compile(r"(\d+)\s*weeks?\s*ago", re.I), "weeks"),
    (re.compile(r"(\d+)\s*months?\s*ago", re.I), "months"),
    (re.compile(r"(\d+)\s*years?\s*ago", re.I), "years"),
    (re.compile(r"\byesterday\b", re.I), "yesterday"),
    (re.compile(r"\btoday\b", re.I), "today"),
    (re.compile(r"\bjust\s*now\b", re.I), "just_now"),
]


def parse_date(
    raw_date: str,
    fetch_time: datetime | None = None,
    locale: str | None = None,
) -> ParsedDate | None:
    """Parse a date string using the layered strategy (PDF §4.1).

    Tries in order:
        1. ISO 8601 / standard datetime formats (strict)
        2. dateutil flexible parser (strict)
        3. Relative expressions (heuristic)
        4. dateparser with locale (heuristic)

    Returns None if all strategies fail.
    """
    if not raw_date or not raw_date.strip():
        return None

    raw_date = raw_date.strip()
    now = fetch_time or datetime.now(timezone.utc)

    # Strategy 1: ISO 8601 / standard format (strictest)
    result = _try_iso_parse(raw_date)
    if result:
        return result

    # Strategy 2: dateutil flexible parser
    result = _try_dateutil(raw_date)
    if result:
        return result

    # Strategy 3: Relative expressions
    result = _try_relative(raw_date, now)
    if result:
        return result

    # Strategy 4: dateparser (broadest, locale-aware)
    result = _try_dateparser(raw_date, locale)
    if result:
        return result

    logger.debug("date_parse_failed", raw_date=raw_date)
    return None


def parse_structured_date(
    date_string: str,
    source: str = "structured",
) -> ParsedDate | None:
    """Parse a date from structured metadata (JSON-LD, meta tags).

    These are always high-confidence since they come from structured markup.
    """
    result = _try_iso_parse(date_string)
    if result:
        return ParsedDate(
            value=result.value,
            confidence=DateConfidence.STRICT,
            source=source,
            raw=date_string,
        )

    result = _try_dateutil(date_string)
    if result:
        return ParsedDate(
            value=result.value,
            confidence=DateConfidence.STRICT,
            source=source,
            raw=date_string,
        )

    return None


def _try_iso_parse(raw: str) -> ParsedDate | None:
    """Try strict ISO 8601 parsing."""
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return ParsedDate(
            value=dt,
            confidence=DateConfidence.STRICT,
            source="iso_8601",
            raw=raw,
        )
    except (ValueError, TypeError):
        return None


def _try_dateutil(raw: str) -> ParsedDate | None:
    """Try dateutil flexible parser."""
    try:
        dt = dateutil_parser.parse(raw, fuzzy=False)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return ParsedDate(
            value=dt,
            confidence=DateConfidence.STRICT,
            source="dateutil",
            raw=raw,
        )
    except (ValueError, TypeError, OverflowError):
        return None


def _try_relative(raw: str, now: datetime) -> ParsedDate | None:
    """Try parsing relative date expressions (PDF §4.1 layer 3)."""
    for pattern, unit in _RELATIVE_PATTERNS:
        match = pattern.search(raw)
        if not match:
            continue

        if unit == "yesterday":
            dt = now - timedelta(days=1)
        elif unit == "today":
            dt = now
        elif unit == "just_now":
            dt = now
        else:
            amount = int(match.group(1))
            if unit == "seconds":
                dt = now - timedelta(seconds=amount)
            elif unit == "minutes":
                dt = now - timedelta(minutes=amount)
            elif unit == "hours":
                dt = now - timedelta(hours=amount)
            elif unit == "days":
                dt = now - timedelta(days=amount)
            elif unit == "weeks":
                dt = now - timedelta(weeks=amount)
            elif unit == "months":
                dt = now - timedelta(days=amount * 30)
            elif unit == "years":
                dt = now - timedelta(days=amount * 365)
            else:
                continue

        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)

        return ParsedDate(
            value=dt,
            confidence=DateConfidence.HEURISTIC,
            source="relative",
            raw=raw,
        )

    return None


def _try_dateparser(raw: str, locale: str | None = None) -> ParsedDate | None:
    """Try dateparser with locale awareness (broadest strategy)."""
    try:
        settings: dict = {
            "RETURN_AS_TIMEZONE_AWARE": True,
            "TIMEZONE": "UTC",
            "PREFER_DATES_FROM": "past",
        }
        if locale:
            settings["LANGUAGE_DETECTION_CONFIDENCE_THRESHOLD"] = 0.5

        languages = [locale] if locale else None
        dt = dateparser.parse(raw, settings=settings, languages=languages)

        if dt is not None:
            return ParsedDate(
                value=dt,
                confidence=DateConfidence.HEURISTIC,
                source="dateparser",
                raw=raw,
            )
    except Exception:
        pass

    return None


def is_within_freshness_window(
    date: datetime,
    max_age_hours: int,
    reference_time: datetime | None = None,
) -> bool:
    """Check if a date falls within the freshness window."""
    now = reference_time or datetime.now(timezone.utc)
    if date.tzinfo is None:
        date = date.replace(tzinfo=timezone.utc)
    age = now - date
    return age <= timedelta(hours=max_age_hours)
