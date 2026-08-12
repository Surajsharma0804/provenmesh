"""Tests for export/serializers.py — entity serialization to flat rows."""
from __future__ import annotations

from provenmesh.export.serializers import (
    INTERNAL_FIELDS,
    flatten_evidenced_field,
    serialize_entity_row,
    serialize_mapping_log_row,
)


class TestFlattenEvidencedField:
    def test_dict_field(self) -> None:
        result = flatten_evidenced_field({
            "value": "OpenAI", "evidence": "...", "confidence": 0.95,
        })
        assert result == "OpenAI"

    def test_none(self) -> None:
        assert flatten_evidenced_field(None) == ""

    def test_plain_string(self) -> None:
        assert flatten_evidenced_field("hello") == "hello"

    def test_list_of_dicts(self) -> None:
        result = flatten_evidenced_field([
            {"value": "Sam Altman"},
            {"value": "Greg Brockman"},
        ])
        assert "Sam Altman" in result
        assert "Greg Brockman" in result
        assert "; " in result

    def test_list_of_strings(self) -> None:
        result = flatten_evidenced_field(["AI", "ML", "NLP"])
        assert "AI" in result
        assert "ML" in result

    def test_dict_missing_value(self) -> None:
        result = flatten_evidenced_field({"other_key": "val"})
        assert result == ""

    def test_empty_list_values_filtered(self) -> None:
        result = flatten_evidenced_field([
            {"value": ""},
            {"value": "Real"},
        ])
        assert result == "Real"

    def test_numeric_value(self) -> None:
        assert flatten_evidenced_field(42) == "42"


class TestInternalFields:
    def test_all_internal_fields_present(self) -> None:
        assert "content_hash" in INTERNAL_FIELDS
        assert "schema_version" in INTERNAL_FIELDS
        assert "correlation_id" in INTERNAL_FIELDS
        assert "raw_s3_key" in INTERNAL_FIELDS


class TestSerializeEntityRow:
    def test_basic(self) -> None:
        row = serialize_entity_row(
            canonical_id="startup_openai",
            entity_name="OpenAI",
            record_type="STARTUP",
            content={
                "description": {"value": "AI company", "confidence": 0.9},
                "website": {"value": "https://openai.com", "confidence": 0.95},
            },
            source_url="https://example.com",
            verification_status="grounded",
            field_order=["description", "website"],
        )
        assert row[0] == "startup_openai"
        assert row[1] == "OpenAI"
        assert row[2] == "STARTUP"
        assert row[3] == "grounded"
        assert row[4] == "https://example.com"
        assert row[5] == "AI company"
        assert row[6] == "https://openai.com"

    def test_skips_internal_fields(self) -> None:
        row = serialize_entity_row(
            "id", "name", "TYPE",
            {"content_hash": "hash", "name": {"value": "Test"}},
            "url", "status",
            field_order=["content_hash", "name"],
        )
        # content_hash should be skipped
        assert len(row) == 6  # 5 header + 1 non-internal field

    def test_missing_fields(self) -> None:
        row = serialize_entity_row(
            "id", "name", "TYPE", {}, "url", "status",
            field_order=["description"],
        )
        assert row[5] == ""  # Missing field returns empty


class TestSerializeMappingLogRow:
    def test_basic(self) -> None:
        row = serialize_mapping_log_row(
            canonical_id="startup_openai",
            entity_name="OpenAI",
            record_type="STARTUP",
            resolution_method="exact",
            resolution_confidence=0.99,
            source_count=3,
            is_seed=True,
            verification_status="grounded",
            grounding_ratio=0.95,
            source_url="https://example.com",
        )
        assert row[0] == "startup_openai"
        assert row[3] == "exact"
        assert row[6] == "Yes"
        assert len(row) == 10

    def test_not_seed(self) -> None:
        row = serialize_mapping_log_row(
            "id", "name", "TYPE", "fuzzy", 0.85, 1, False, "partial", 0.5, "url",
        )
        assert row[6] == "No"
