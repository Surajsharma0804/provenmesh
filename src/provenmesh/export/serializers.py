"""Export serializers — convert internal entities to Sheets-ready rows (v2 §32).

Strips internal metadata (content_hash, schema_version, correlation_id)
and flattens evidence-first fields to plain values for export.
"""

from __future__ import annotations

from typing import Any

from provenmesh.observability.logging import get_logger

logger = get_logger(__name__)

# Internal fields that should never appear in Sheets export
INTERNAL_FIELDS = {
    "content_hash", "schema_version", "correlation_id",
    "raw_s3_key", "processing_state", "verification_status",
    "resolution_method", "resolution_confidence", "source_count",
    "prompt_version", "extraction_provider", "fetch_tier",
}


def flatten_evidenced_field(field_data: Any) -> str:
    """Extract the plain value from an evidence-first field.

    Input:  {"value": "OpenAI", "evidence": "...", "confidence": 0.95}
    Output: "OpenAI"
    """
    if field_data is None:
        return ""
    if isinstance(field_data, dict):
        return str(field_data.get("value", ""))
    if isinstance(field_data, list):
        values = []
        for item in field_data:
            if isinstance(item, dict):
                values.append(str(item.get("value", "")))
            else:
                values.append(str(item))
        return "; ".join(v for v in values if v)
    return str(field_data)


def serialize_entity_row(
    canonical_id: str,
    entity_name: str,
    record_type: str,
    content: dict[str, Any],
    source_url: str,
    verification_status: str,
    field_order: list[str],
) -> list[str]:
    """Serialize an entity to a flat row for Sheets export.

    Always starts with: [canonical_id, entity_name, record_type, status, source_url]
    Then adds type-specific fields in the given order.
    """
    row: list[str] = [
        canonical_id,
        entity_name,
        record_type,
        verification_status,
        source_url,
    ]

    for field_name in field_order:
        if field_name in INTERNAL_FIELDS:
            continue
        field_data = content.get(field_name)
        row.append(flatten_evidenced_field(field_data))

    return row


def serialize_mapping_log_row(
    canonical_id: str,
    entity_name: str,
    record_type: str,
    resolution_method: str,
    resolution_confidence: float,
    source_count: int,
    is_seed: bool,
    verification_status: str,
    grounding_ratio: float,
    source_url: str,
) -> list[str]:
    """Serialize an entity mapping log entry for tab 6."""
    return [
        canonical_id,
        entity_name,
        record_type,
        resolution_method,
        str(round(resolution_confidence, 3)),
        str(source_count),
        "Yes" if is_seed else "No",
        verification_status,
        str(round(grounding_ratio, 2)),
        source_url,
    ]
