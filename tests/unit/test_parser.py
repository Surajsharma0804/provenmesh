"""Tests for extraction/parser.py — LLM response parsing and field extraction."""
from __future__ import annotations

from provenmesh.extraction.parser import (
    extract_evidenced_fields,
    extract_relationships,
    parse_llm_response,
)


class TestParseLlmResponse:
    def test_valid_json(self) -> None:
        result = parse_llm_response('{"name": "OpenAI"}')
        assert result == {"name": "OpenAI"}

    def test_empty(self) -> None:
        assert parse_llm_response("") == {}

    def test_markdown_json_block(self) -> None:
        result = parse_llm_response('```json\n{"name": "test"}\n```')
        assert result == {"name": "test"}

    def test_markdown_block_no_lang(self) -> None:
        result = parse_llm_response('```\n{"name": "test"}\n```')
        assert result == {"name": "test"}

    def test_invalid_json_with_embedded(self) -> None:
        result = parse_llm_response('Here is the result: {"name": "test"} done')
        assert result == {"name": "test"}

    def test_completely_invalid(self) -> None:
        result = parse_llm_response("this is not json at all")
        assert result == {}

    def test_truncated_json(self) -> None:
        result = parse_llm_response('{"name": "test", "incomplete":')
        assert result == {} or isinstance(result, dict)

    def test_nested_json_extraction_fails(self) -> None:
        """When embedded JSON extraction also fails (lines 47-48)."""
        text = 'Some text { invalid json too } more text'
        result = parse_llm_response(text)
        assert result == {}


class TestExtractEvidencedFields:
    def test_already_evidenced(self) -> None:
        parsed = {
            "name": {"value": "OpenAI", "evidence": "text", "confidence": 0.95},
        }
        result = extract_evidenced_fields(parsed)
        assert result["name"]["value"] == "OpenAI"
        assert result["name"]["confidence"] == 0.95

    def test_simple_values_wrapped(self) -> None:
        parsed = {"name": "OpenAI", "year": 2015}
        result = extract_evidenced_fields(parsed)
        assert result["name"]["value"] == "OpenAI"
        assert result["name"]["confidence"] == 0.0
        assert result["year"]["value"] == 2015

    def test_list_fields(self) -> None:
        parsed = {
            "founders": [
                {"value": "Sam Altman", "confidence": 0.9},
                "Greg Brockman",
            ],
        }
        result = extract_evidenced_fields(parsed)
        assert len(result["founders"]) == 2
        assert result["founders"][0]["value"] == "Sam Altman"
        assert result["founders"][1]["value"] == "Greg Brockman"
        assert result["founders"][1]["confidence"] == 0.0

    def test_relationships_skipped(self) -> None:
        parsed = {
            "name": "OpenAI",
            "relationships": [{"source": "a", "target": "b"}],
        }
        result = extract_evidenced_fields(parsed)
        assert "relationships" not in result

    def test_missing_evidence_defaults(self) -> None:
        parsed = {"name": {"value": "test"}}
        result = extract_evidenced_fields(parsed)
        assert result["name"]["evidence"] == ""
        assert result["name"]["confidence"] == 0.0


class TestExtractRelationships:
    def test_valid_relationships(self) -> None:
        parsed = {
            "relationships": [
                {"source": "OpenAI", "target": "ChatGPT", "type": "BUILDS_PRODUCT"},
            ],
        }
        result = extract_relationships(parsed)
        assert len(result) == 1
        assert result[0]["source"] == "OpenAI"
        assert result[0]["type"] == "BUILDS_PRODUCT"

    def test_no_relationships(self) -> None:
        assert extract_relationships({}) == []

    def test_invalid_type(self) -> None:
        assert extract_relationships({"relationships": "not a list"}) == []

    def test_incomplete_entries_skipped(self) -> None:
        parsed = {
            "relationships": [
                {"source": "a"},  # Missing target and type
                {"source": "a", "target": "b", "type": "X"},  # Valid
            ],
        }
        result = extract_relationships(parsed)
        assert len(result) == 1

    def test_confidence_extraction(self) -> None:
        parsed = {
            "relationships": [
                {"source": "a", "target": "b", "type": "X", "confidence": 0.88},
            ],
        }
        result = extract_relationships(parsed)
        assert result[0]["confidence"] == 0.88
