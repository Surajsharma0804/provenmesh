"""Tests for export/validate.py — data validation for export."""
from __future__ import annotations

from provenmesh.export.validate import (
    REQUIRED_FIELDS_BY_TYPE,
    ValidationResult,
    validate_for_export,
)


class TestValidateForExport:
    def test_valid_startup(self) -> None:
        content = {
            "entityName": {"value": "OpenAI", "confidence": 0.99},
            "description": {"value": "AI company", "confidence": 0.95},
        }
        result = validate_for_export(
            canonical_id="startup_openai",
            record_type="STARTUP",
            content=content,
            verification_status="grounded",
            schema_valid=True,
            resolution_method="exact",
        )
        assert isinstance(result, ValidationResult)
        assert result.is_valid is True

    def test_empty_content(self) -> None:
        result = validate_for_export(
            canonical_id="startup_test",
            record_type="STARTUP",
            content={},
            verification_status="unverified",
            schema_valid=False,
            resolution_method="unresolved",
        )
        assert isinstance(result, ValidationResult)

    def test_unknown_type(self) -> None:
        result = validate_for_export(
            canonical_id="test_id",
            record_type="UNKNOWN_TYPE",
            content={"name": "test"},
            verification_status="unverified",
            schema_valid=False,
            resolution_method="unresolved",
        )
        assert isinstance(result, ValidationResult)

    def test_product(self) -> None:
        content = {
            "entityName": {"value": "ChatGPT", "confidence": 0.99},
        }
        result = validate_for_export(
            canonical_id="product_chatgpt",
            record_type="PRODUCT",
            content=content,
            verification_status="grounded",
            schema_valid=True,
            resolution_method="exact",
        )
        assert isinstance(result, ValidationResult)

    def test_string_field_values(self) -> None:
        """Test when content fields are plain strings, not dicts (line 72-73)."""
        content = {
            "entityName": "ChatGPT",  # Plain string, not dict
            "description": "An AI chatbot",
        }
        result = validate_for_export(
            canonical_id="product_chatgpt",
            record_type="PRODUCT",
            content=content,
            verification_status="grounded",
            schema_valid=True,
            resolution_method="exact",
        )
        assert isinstance(result, ValidationResult)


class TestRequiredFieldsByType:
    def test_startup_has_required_fields(self) -> None:
        assert "STARTUP" in REQUIRED_FIELDS_BY_TYPE
        assert len(REQUIRED_FIELDS_BY_TYPE["STARTUP"]) > 0

    def test_product_has_required_fields(self) -> None:
        assert "PRODUCT" in REQUIRED_FIELDS_BY_TYPE


class TestValidationResult:
    def test_creation(self) -> None:
        r = ValidationResult(is_valid=True, errors=[])
        assert r.is_valid is True
        assert r.errors == []

    def test_with_errors(self) -> None:
        r = ValidationResult(is_valid=False, errors=["missing entityName"])
        assert r.is_valid is False
        assert len(r.errors) == 1

