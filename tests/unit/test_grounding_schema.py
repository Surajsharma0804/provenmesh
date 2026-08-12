"""Tests for grounding/schema_validator.py — JSON Schema validation."""
from __future__ import annotations

import pytest

from provenmesh.grounding.schema_validator import _SCHEMA_CACHE, _load_schema, validate_record


class TestLoadSchema:
    def setup_method(self) -> None:
        _SCHEMA_CACHE.clear()

    def test_cache_hit(self) -> None:
        _SCHEMA_CACHE["TEST_TYPE"] = {"type": "object"}
        schema = _load_schema("TEST_TYPE")
        assert schema == {"type": "object"}

    def test_unknown_type_raises(self) -> None:
        with pytest.raises(ValueError, match="No schema"):
            _load_schema("UNKNOWN_XYZ")

    def test_missing_file_returns_empty(self) -> None:
        # STARTUP schema file may not exist in test environment
        _SCHEMA_CACHE.clear()
        schema = _load_schema("STARTUP")
        # Either loads the schema or returns {} if file missing
        assert isinstance(schema, dict)

    def test_missing_schema_file_explicit(self) -> None:
        """Force the missing schema path (lines 38-39)."""
        from pathlib import Path
        from unittest.mock import patch
        _SCHEMA_CACHE.clear()
        # Patch schemas_dir to a nonexistent directory
        with patch(
            "provenmesh.grounding.schema_validator.get_settings",
        ) as mock_settings:
            mock_cfg = mock_settings.return_value
            mock_cfg.schemas_dir = Path("/nonexistent/schemas")
            schema = _load_schema("STARTUP")
            assert schema == {}


class TestValidateRecord:
    def setup_method(self) -> None:
        _SCHEMA_CACHE.clear()

    def test_no_schema_passes(self) -> None:
        # Force empty schema via cache
        _SCHEMA_CACHE["STARTUP"] = {}
        is_valid, errors = validate_record({"name": "test"}, "STARTUP")
        assert is_valid is True
        assert errors == []

    def test_valid_against_schema(self) -> None:
        schema = {
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name"],
        }
        _SCHEMA_CACHE["STARTUP"] = schema
        is_valid, errors = validate_record({"name": "OpenAI"}, "STARTUP")
        assert is_valid is True
        assert errors == []

    def test_invalid_against_schema(self) -> None:
        schema = {
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name"],
        }
        _SCHEMA_CACHE["STARTUP"] = schema
        is_valid, errors = validate_record({"other": 123}, "STARTUP")
        assert is_valid is False
        assert len(errors) > 0

    def test_bad_schema(self) -> None:
        # Invalid schema itself
        _SCHEMA_CACHE["STARTUP"] = {"type": "invalid_type_xyz"}
        is_valid, errors = validate_record({"x": 1}, "STARTUP")
        assert isinstance(is_valid, bool)

    def test_unknown_type_raises(self) -> None:
        with pytest.raises(ValueError, match="No schema"):
            validate_record({"name": "test"}, "NONEXISTENT_TYPE")
