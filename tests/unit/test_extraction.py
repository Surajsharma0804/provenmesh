"""Unit tests for extraction — chunking and LLM response parsing."""

from __future__ import annotations

from provenmesh.extraction.chunking import (
    chunk_text,
    estimate_tokens,
)
from provenmesh.extraction.parser import (
    extract_evidenced_fields,
    extract_relationships,
    parse_llm_response,
)


class TestTokenEstimation:
    """Tests for token count estimation."""

    def test_empty_string(self) -> None:
        assert estimate_tokens("") == 1

    def test_normal_text(self) -> None:
        tokens = estimate_tokens("Hello world this is a test")
        assert tokens > 0


class TestChunking:
    """Tests for semantic text chunking."""

    def test_single_chunk(self) -> None:
        text = "Short text that fits in one chunk."
        chunks = chunk_text(text, max_tokens=1000)
        assert len(chunks) == 1
        assert chunks[0].chunk_index == 0
        assert chunks[0].total_chunks == 1

    def test_multiple_chunks(self) -> None:
        paragraphs = ["Paragraph " + str(i) + ". " * 100 for i in range(20)]
        text = "\n\n".join(paragraphs)
        chunks = chunk_text(text, max_tokens=200)
        assert len(chunks) > 1
        for i, chunk in enumerate(chunks):
            assert chunk.chunk_index == i
            assert chunk.total_chunks == len(chunks)

    def test_empty_text(self) -> None:
        assert chunk_text("") == []

    def test_preserves_paragraphs(self) -> None:
        text = "First paragraph.\n\nSecond paragraph.\n\nThird paragraph."
        chunks = chunk_text(text, max_tokens=10000)
        assert len(chunks) == 1
        assert "First" in chunks[0].text
        assert "Third" in chunks[0].text


class TestLLMResponseParsing:
    """Tests for LLM response parsing."""

    def test_valid_json(self) -> None:
        raw = '{"entityName": {"value": "OpenAI", "evidence": "test", "confidence": 0.9}}'
        result = parse_llm_response(raw)
        assert result["entityName"]["value"] == "OpenAI"

    def test_markdown_wrapped_json(self) -> None:
        raw = '```json\n{"key": "value"}\n```'
        result = parse_llm_response(raw)
        assert result["key"] == "value"

    def test_empty_response(self) -> None:
        assert parse_llm_response("") == {}

    def test_invalid_json(self) -> None:
        result = parse_llm_response("not json at all")
        assert result == {}

    def test_json_in_text(self) -> None:
        raw = 'Here is the data: {"key": "value"} end'
        result = parse_llm_response(raw)
        assert result.get("key") == "value"


class TestEvidencedFieldExtraction:
    """Tests for normalizing LLM output to evidence-first format."""

    def test_already_evidenced(self) -> None:
        parsed = {
            "entityName": {"value": "OpenAI", "evidence": "test", "confidence": 0.9},
        }
        result = extract_evidenced_fields(parsed)
        assert result["entityName"]["value"] == "OpenAI"
        assert result["entityName"]["confidence"] == 0.9

    def test_wrap_simple_values(self) -> None:
        parsed = {"entityName": "OpenAI"}
        result = extract_evidenced_fields(parsed)
        assert result["entityName"]["value"] == "OpenAI"
        assert result["entityName"]["confidence"] == 0.0


class TestRelationshipExtraction:
    """Tests for relationship candidate extraction."""

    def test_valid_relationships(self) -> None:
        parsed = {
            "relationships": [
                {"source": "Sam Altman", "target": "OpenAI", "type": "FOUNDED_BY", "confidence": 0.9},  # noqa: E501
            ]
        }
        result = extract_relationships(parsed)
        assert len(result) == 1
        assert result[0]["type"] == "FOUNDED_BY"

    def test_no_relationships(self) -> None:
        assert extract_relationships({}) == []
        assert extract_relationships({"relationships": "not a list"}) == []

    def test_incomplete_relationships_filtered(self) -> None:
        parsed = {
            "relationships": [
                {"source": "A"},  # Missing target and type
                {"source": "B", "target": "C", "type": "WORKS_AT"},
            ]
        }
        result = extract_relationships(parsed)
        assert len(result) == 1
