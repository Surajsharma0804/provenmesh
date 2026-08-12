"""Schema validation — JSON Schema enforcement for extracted records."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import jsonschema

from provenmesh.config.settings import get_settings
from provenmesh.observability.logging import get_logger

logger = get_logger(__name__)

_SCHEMA_CACHE: dict[str, dict] = {}


def _load_schema(record_type: str) -> dict:
    """Load and cache a JSON schema for a record type."""
    if record_type in _SCHEMA_CACHE:
        return _SCHEMA_CACHE[record_type]

    settings = get_settings()
    schema_map = {
        "STARTUP": "startup.json",
        "PRODUCT": "product.json",
        "PAPER": "paper.json",
        "JOB": "job.json",
        "NEWS_SIGNAL": "news_signal.json",
    }

    filename = schema_map.get(record_type)
    if not filename:
        raise ValueError(f"No schema for record type: {record_type}")

    schema_path = settings.schemas_dir / filename
    if not schema_path.exists():
        logger.warning("schema_file_missing", path=str(schema_path))
        return {}

    with open(schema_path) as f:
        schema = json.load(f)

    _SCHEMA_CACHE[record_type] = schema
    return schema


def validate_record(
    record: dict[str, Any],
    record_type: str,
) -> tuple[bool, list[str]]:
    """Validate a record against its JSON schema.

    Returns (is_valid, list_of_errors).
    """
    schema = _load_schema(record_type)
    if not schema:
        return True, []  # No schema = pass

    errors: list[str] = []
    try:
        jsonschema.validate(record, schema)
        return True, []
    except jsonschema.ValidationError as e:
        errors.append(f"{e.json_path}: {e.message}")
    except jsonschema.SchemaError as e:
        errors.append(f"Schema error: {e.message}")

    return False, errors
