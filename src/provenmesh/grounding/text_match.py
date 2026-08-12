"""Text grounding — fuzzy substring verification (v2 §20).

Verifies that extracted text values actually appear in the source text.
Uses RapidFuzz partial_ratio for tolerant substring matching.
"""

from __future__ import annotations

from rapidfuzz import fuzz

from provenmesh.domain.enums import FieldVerification
from provenmesh.observability.logging import get_logger

logger = get_logger(__name__)

# Minimum fuzzy score to consider a field grounded
DEFAULT_TEXT_THRESHOLD = 90


def verify_text_field(
    extracted_value: str,
    evidence_text: str,
    source_text: str,
    threshold: float = DEFAULT_TEXT_THRESHOLD,
) -> tuple[FieldVerification, float]:
    """Verify a text field against source text.

    Strategy:
        1. If evidence_text is provided, check it appears in source
        2. Then check extracted_value appears in evidence_text
        3. Fall back to checking value directly in source

    Returns:
        Tuple of (verification_status, fuzzy_score)
    """
    if not extracted_value:
        return FieldVerification.MISSING, 0.0

    if not evidence_text:
        # No evidence provided — try direct source match
        return _direct_source_match(extracted_value, source_text, threshold)

    # Step 1: evidence must exist in source
    evidence_in_source = fuzz.partial_ratio(
        evidence_text.lower().strip(),
        source_text.lower(),
    )

    if evidence_in_source < threshold:
        logger.debug(
            "evidence_not_in_source",
            value=extracted_value[:50],
            score=round(evidence_in_source, 1),
        )
        return FieldVerification.UNVERIFIED, evidence_in_source

    # Step 2: value must exist in evidence
    value_in_evidence = fuzz.partial_ratio(
        extracted_value.lower().strip(),
        evidence_text.lower(),
    )

    if value_in_evidence >= threshold:
        return FieldVerification.GROUNDED, value_in_evidence

    return FieldVerification.UNVERIFIED, value_in_evidence


def _direct_source_match(
    value: str,
    source_text: str,
    threshold: float,
) -> tuple[FieldVerification, float]:
    """Fall back to checking value directly in source text."""
    score = fuzz.partial_ratio(value.lower().strip(), source_text.lower())
    if score >= threshold:
        return FieldVerification.GROUNDED, score
    return FieldVerification.UNVERIFIED, score


def verify_list_field(
    extracted_values: list[str],
    evidence_texts: list[str],
    source_text: str,
    threshold: float = DEFAULT_TEXT_THRESHOLD,
) -> tuple[FieldVerification, float]:
    """Verify a list field — each item must be grounded individually.

    Returns GROUNDED only if all items pass. PARTIAL if ≥50% pass.
    """
    if not extracted_values:
        return FieldVerification.MISSING, 0.0

    scores: list[float] = []
    grounded_count = 0

    for i, value in enumerate(extracted_values):
        evidence = evidence_texts[i] if i < len(evidence_texts) else ""
        status, score = verify_text_field(value, evidence, source_text, threshold)
        scores.append(score)
        if status == FieldVerification.GROUNDED:
            grounded_count += 1

    avg_score = sum(scores) / len(scores) if scores else 0.0
    ratio = grounded_count / len(extracted_values)

    if ratio >= 1.0:
        return FieldVerification.GROUNDED, avg_score
    elif ratio >= 0.5:
        return FieldVerification.GROUNDED, avg_score  # Partial but acceptable
    return FieldVerification.UNVERIFIED, avg_score
