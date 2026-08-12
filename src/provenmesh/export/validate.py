"""Export validation — pre-export quality gates (v2 §33).

No record reaches Sheets unless ALL four gates pass:
    1. schema_valid = true
    2. verification_status != unverified
    3. required_fields_valid = true
    4. entity_resolution_valid = true
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from provenmesh.observability.logging import get_logger

logger = get_logger(__name__)

REQUIRED_FIELDS_BY_TYPE: dict[str, list[str]] = {
    "STARTUP": ["entityName"],
    "PRODUCT": ["entityName"],
    "PAPER": ["title"],
    "JOB": ["title", "company"],
    "NEWS_SIGNAL": ["title"],
}


@dataclass
class ValidationResult:
    """Result of pre-export validation."""

    is_valid: bool = False
    errors: list[str] = field(default_factory=list)

    def add_error(self, error: str) -> None:
        self.errors.append(error)
        self.is_valid = False


def validate_for_export(
    canonical_id: str,
    record_type: str,
    content: dict[str, Any],
    verification_status: str,
    schema_valid: bool,
    resolution_method: str,
) -> ValidationResult:
    """Run all four export quality gates.

    Gate 1: Schema validation passed
    Gate 2: Verification status is grounded or partial
    Gate 3: Required fields are present and non-empty
    Gate 4: Entity has been resolved (has canonical_id)
    """
    result = ValidationResult(is_valid=True)

    # Gate 1: Schema valid
    if not schema_valid:
        result.add_error(f"Schema validation failed for {canonical_id}")

    # Gate 2: Verification status
    if verification_status in ("unverified", "rejected"):
        result.add_error(f"Verification status is '{verification_status}' — cannot export")

    # Gate 3: Required fields
    required = REQUIRED_FIELDS_BY_TYPE.get(record_type, [])
    for field_name in required:
        field_data = content.get(field_name, {})
        value = ""
        if isinstance(field_data, dict):
            value = str(field_data.get("value", ""))
        elif isinstance(field_data, str):
            value = field_data

        if not value.strip():
            result.add_error(f"Required field '{field_name}' is empty")

    # Gate 4: Entity resolution
    if resolution_method == "unresolved":
        result.add_error(f"Entity '{canonical_id}' has not been resolved")

    if result.errors:
        logger.debug(
            "export_validation_failed",
            canonical_id=canonical_id,
            errors=result.errors,
        )

    return result
