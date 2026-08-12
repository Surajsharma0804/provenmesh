"""Numeric grounding — number verification with tolerance (v2 §20).

Normalizes numeric representations ($6.6B, 6.6 billion, 6600000000)
and compares with configurable tolerance (default ±1%).
"""

from __future__ import annotations

import re

from provenmesh.domain.enums import FieldVerification
from provenmesh.observability.logging import get_logger

logger = get_logger(__name__)

# Numeric suffixes and their multipliers
SUFFIXES: dict[str, float] = {
    "k": 1_000,
    "K": 1_000,
    "thousand": 1_000,
    "m": 1_000_000,
    "M": 1_000_000,
    "million": 1_000_000,
    "mm": 1_000_000,
    "b": 1_000_000_000,
    "B": 1_000_000_000,
    "billion": 1_000_000_000,
    "bn": 1_000_000_000,
    "t": 1_000_000_000_000,
    "T": 1_000_000_000_000,
    "trillion": 1_000_000_000_000,
}

# Regex to extract numeric values
NUMERIC_PATTERN = re.compile(
    r"[\$€£¥]?\s*(\d[\d,]*\.?\d*)\s*"
    r"(k|K|thousand|m|M|million|mm|b|B|billion|bn|t|T|trillion)?",
)


def parse_numeric(text: str) -> float | None:
    """Parse a numeric string into a float, handling suffixes and currency.

    Examples:
        "$6.6B" → 6_600_000_000
        "6.6 billion" → 6_600_000_000
        "1,700" → 1700
        "$80 billion" → 80_000_000_000
    """
    if not text:
        return None

    text = text.strip()

    # Try direct float parse first (handles simple numbers)
    clean = text.replace(",", "").replace("$", "").replace("€", "").replace("£", "")
    clean = clean.replace("¥", "").strip()

    match = NUMERIC_PATTERN.search(text)
    if not match:
        try:
            return float(clean)
        except ValueError:
            return None

    number_str = match.group(1).replace(",", "")
    suffix = match.group(2)

    try:
        value = float(number_str)
    except ValueError:
        return None

    if suffix and suffix in SUFFIXES:
        value *= SUFFIXES[suffix]

    return value


def verify_numeric_field(
    extracted_value: str,
    evidence_text: str,
    source_text: str,
    tolerance: float = 0.01,
) -> tuple[FieldVerification, float]:
    """Verify a numeric field against source text.

    Strategy:
        1. Parse the extracted value to a number
        2. Find all numbers in the evidence/source text
        3. Check if any number is within tolerance

    Args:
        tolerance: Fractional tolerance (0.01 = ±1%)

    Returns:
        Tuple of (verification_status, match_score)
    """
    extracted_num = parse_numeric(extracted_value)
    if extracted_num is None:
        return FieldVerification.MISSING, 0.0

    # Search in evidence first, then source
    search_texts = []
    if evidence_text:
        search_texts.append(evidence_text)
    search_texts.append(source_text)

    for text in search_texts:
        numbers_in_text = extract_all_numbers(text)
        for source_num in numbers_in_text:
            if source_num == 0:
                continue
            relative_diff = abs(extracted_num - source_num) / max(abs(source_num), 1e-10)
            if relative_diff <= tolerance:
                score = 1.0 - relative_diff
                return FieldVerification.GROUNDED, score

    return FieldVerification.UNVERIFIED, 0.0


def extract_all_numbers(text: str) -> list[float]:
    """Extract all numeric values from a text string."""
    results: list[float] = []
    for match in NUMERIC_PATTERN.finditer(text):
        number_str = match.group(1).replace(",", "")
        suffix = match.group(2)
        try:
            value = float(number_str)
            if suffix and suffix in SUFFIXES:
                value *= SUFFIXES[suffix]
            results.append(value)
        except ValueError:
            continue
    return results
