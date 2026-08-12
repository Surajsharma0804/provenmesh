"""Grounding verifier — high-level record verification orchestrator (v2 §20-22).

Dispatches field verification to specialized sub-modules based on field type
and aggregates results into a record-level verification status.
"""

from __future__ import annotations

from provenmesh.domain.enums import FieldVerification, VerificationStatus
from provenmesh.domain.evidence import EvidenceRecord
from provenmesh.grounding.date_match import verify_date_field
from provenmesh.grounding.numeric_match import verify_numeric_field
from provenmesh.grounding.text_match import verify_text_field
from provenmesh.observability.logging import get_logger

logger = get_logger(__name__)

# Field names that should use numeric verification
NUMERIC_FIELDS = {
    "fundingTotal", "lastFundingRound", "employeeCount",
    "salaryMin", "salaryMax", "githubStars", "citations",
    "valuation", "revenue", "price", "pricing",
}

# Field names that should use date verification
DATE_FIELDS = {
    "foundedDate", "launchDate", "publishedDate", "postedDate",
    "closingDate", "lastUpdated", "publishedAt",
}

# Field names that should use URL verification
URL_FIELDS = {
    "website", "githubUrl", "linkedinUrl", "twitterUrl",
    "crunchbaseUrl", "productHuntUrl", "arxivUrl",
}


def classify_field(field_name: str) -> str:
    """Classify a field into its verification strategy."""
    if field_name in NUMERIC_FIELDS:
        return "numeric"
    if field_name in DATE_FIELDS:
        return "date"
    if field_name in URL_FIELDS:
        return "url"
    return "text"


def verify_field(
    field_name: str,
    extracted_value: str,
    evidence_text: str,
    source_text: str,
) -> tuple[FieldVerification, float]:
    """Route field verification to the appropriate sub-module."""
    field_type = classify_field(field_name)

    if field_type == "numeric":
        return verify_numeric_field(extracted_value, evidence_text, source_text)
    elif field_type == "date":
        return verify_date_field(extracted_value, evidence_text, source_text)
    elif field_type == "url":
        return _verify_url_field(extracted_value, evidence_text, source_text)
    else:
        return verify_text_field(extracted_value, evidence_text, source_text)


def _verify_url_field(
    extracted_value: str,
    evidence_text: str,
    source_text: str,
) -> tuple[FieldVerification, float]:
    """Verify a URL field — canonicalize and check presence in source."""
    from provenmesh.security.sanitization import sanitize_url

    if not extracted_value:
        return FieldVerification.MISSING, 0.0

    canonical = sanitize_url(extracted_value)
    source_lower = source_text.lower()

    # Check if the URL or its core domain appears in source
    if canonical.lower() in source_lower:
        return FieldVerification.GROUNDED, 1.0

    # Check without protocol
    no_protocol = canonical.replace("https://", "").replace("http://", "")
    if no_protocol.lower() in source_lower:
        return FieldVerification.GROUNDED, 0.95

    return FieldVerification.UNVERIFIED, 0.0


def aggregate_verification(
    field_results: list[tuple[str, FieldVerification, float]],
) -> tuple[VerificationStatus, float]:
    """Aggregate field-level results into record-level verification status.

    Rules (v2 §22):
        - 100% grounded → GROUNDED
        - ≥ 50% grounded → PARTIAL
        - Any field → UNVERIFIED
        - Empty → UNVERIFIED
    """
    if not field_results:
        return VerificationStatus.UNVERIFIED, 0.0

    total = len(field_results)
    grounded = sum(1 for _, status, _ in field_results if status == FieldVerification.GROUNDED)
    conflicting = sum(1 for _, status, _ in field_results if status == FieldVerification.CONFLICTING)

    if conflicting > 0:
        return VerificationStatus.REJECTED, grounded / total

    ratio = grounded / total
    if ratio >= 1.0:
        return VerificationStatus.GROUNDED, ratio
    elif ratio >= 0.5:
        return VerificationStatus.PARTIAL, ratio
    return VerificationStatus.UNVERIFIED, ratio
