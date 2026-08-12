"""Date grounding — date verification with tolerance (v2 §20).

Normalizes date representations (August 12, 2026 / 2026-08-12 / 12/08/2026)
and compares with configurable tolerance (default ±1 day).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

import dateparser

from provenmesh.domain.enums import FieldVerification
from provenmesh.observability.logging import get_logger

logger = get_logger(__name__)

DEFAULT_DATE_TOLERANCE_DAYS = 1


def parse_date_value(text: str) -> Optional[datetime]:
    """Parse any date string into a datetime."""
    if not text or not text.strip():
        return None
    try:
        return dateparser.parse(
            text.strip(),
            settings={"RETURN_AS_TIMEZONE_AWARE": True, "TIMEZONE": "UTC"},
        )
    except Exception:
        return None


def verify_date_field(
    extracted_value: str,
    evidence_text: str,
    source_text: str,
    tolerance_days: int = DEFAULT_DATE_TOLERANCE_DAYS,
) -> tuple[FieldVerification, float]:
    """Verify a date field against source text.

    Strategy:
        1. Parse the extracted date value
        2. Find all dates in the evidence/source text
        3. Check if any date is within tolerance

    Returns:
        Tuple of (verification_status, match_score)
    """
    extracted_date = parse_date_value(extracted_value)
    if extracted_date is None:
        return FieldVerification.MISSING, 0.0

    # Search in evidence first, then source
    search_texts = []
    if evidence_text:
        search_texts.append(evidence_text)
    search_texts.append(source_text)

    tolerance = timedelta(days=tolerance_days)

    for text in search_texts:
        source_dates = extract_dates_from_text(text)
        for source_date in source_dates:
            diff = abs((extracted_date - source_date).total_seconds())
            tolerance_seconds = tolerance.total_seconds()
            if diff <= tolerance_seconds:
                score = 1.0 - (diff / max(tolerance_seconds, 1))
                return FieldVerification.GROUNDED, max(score, 0.0)

    return FieldVerification.UNVERIFIED, 0.0


def extract_dates_from_text(text: str) -> list[datetime]:
    """Extract date-like values from text using multiple strategies."""
    import re

    dates: list[datetime] = []

    # Strategy 1: ISO 8601 patterns
    iso_pattern = re.compile(r"\d{4}-\d{2}-\d{2}(?:T\d{2}:\d{2}:\d{2})?")
    for match in iso_pattern.finditer(text):
        parsed = parse_date_value(match.group())
        if parsed:
            dates.append(parsed)

    # Strategy 2: Common written date patterns
    written_patterns = [
        r"(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s+\d{4}",
        r"\d{1,2}\s+(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{4}",
        r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{1,2},?\s+\d{4}",
    ]
    for pattern in written_patterns:
        for match in re.finditer(pattern, text, re.IGNORECASE):
            parsed = parse_date_value(match.group())
            if parsed:
                dates.append(parsed)

    return dates
