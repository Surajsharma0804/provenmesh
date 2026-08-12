"""Tests for graph/relationships.py — relationship validation and extraction."""
from __future__ import annotations

from provenmesh.graph.relationships import (
    build_relationship_record,
    extract_implicit_relationships,
    validate_relationship,
)


class TestValidateRelationship:
    def test_valid_founded_by(self) -> None:
        assert validate_relationship("STARTUP", "STARTUP", "FOUNDED_BY") is True

    def test_valid_builds_product(self) -> None:
        assert validate_relationship("STARTUP", "PRODUCT", "BUILDS_PRODUCT") is True

    def test_valid_works_at(self) -> None:
        assert validate_relationship("JOB", "STARTUP", "WORKS_AT") is True

    def test_invalid_type(self) -> None:
        assert validate_relationship("STARTUP", "STARTUP", "INVALID") is False

    def test_valid_cites(self) -> None:
        assert validate_relationship("PAPER", "PAPER", "CITES") is True


class TestBuildRelationshipRecord:
    def test_basic_creation(self) -> None:
        record = build_relationship_record(
            source_id="startup_openai",
            target_id="product_chatgpt",
            relation_type="BUILDS_PRODUCT",
            confidence=0.95,
            source_url="https://example.com",
            content_hash="hash1",
            evidence_text="OpenAI builds ChatGPT",
        )
        assert record.source_id == "startup_openai"
        assert record.target_id == "product_chatgpt"
        assert record.confidence == 0.95

    def test_confidence_clamping_high(self) -> None:
        record = build_relationship_record(
            "a", "b", "CITES", confidence=1.5,
        )
        assert record.confidence == 1.0

    def test_confidence_clamping_low(self) -> None:
        record = build_relationship_record(
            "a", "b", "CITES", confidence=-0.5,
        )
        assert record.confidence == 0.0

    def test_evidence_truncation(self) -> None:
        record = build_relationship_record(
            "a", "b", "CITES", confidence=0.9,
            evidence_text="x" * 2000,
        )
        assert len(record.evidence_text) == 1000


class TestExtractImplicitRelationships:
    def test_startup_products(self) -> None:
        entity_data = {
            "products": [
                {"value": "ChatGPT"},
                {"value": "DALL-E"},
            ],
        }
        rels = extract_implicit_relationships(
            entity_data, "STARTUP", "startup_openai",
        )
        assert len(rels) == 2
        assert rels[0]["type"] == "BUILDS_PRODUCT"
        assert rels[0]["target"] == "ChatGPT"

    def test_startup_products_dict_format(self) -> None:
        entity_data = {
            "products": {"value": ["ChatGPT", "DALL-E"]},
        }
        rels = extract_implicit_relationships(
            entity_data, "STARTUP", "startup_openai",
        )
        assert len(rels) == 2

    def test_job_company(self) -> None:
        entity_data = {
            "company": {"value": "OpenAI"},
        }
        rels = extract_implicit_relationships(
            entity_data, "JOB", "job_ml-engineer-openai",
        )
        assert len(rels) == 1
        assert rels[0]["type"] == "WORKS_AT"
        assert rels[0]["target"] == "OpenAI"

    def test_job_company_string(self) -> None:
        entity_data = {"company": "OpenAI"}
        rels = extract_implicit_relationships(
            entity_data, "JOB", "job_ml-engineer",
        )
        assert len(rels) == 1

    def test_paper_no_relationships(self) -> None:
        rels = extract_implicit_relationships(
            {"title": "Test Paper"}, "PAPER", "paper_test",
        )
        assert rels == []

    def test_startup_no_products(self) -> None:
        rels = extract_implicit_relationships(
            {"description": "A company"}, "STARTUP", "startup_test",
        )
        assert rels == []

    def test_startup_products_empty_name(self) -> None:
        entity_data = {"products": [{"value": ""}, {"value": "Real"}]}
        rels = extract_implicit_relationships(
            entity_data, "STARTUP", "startup_test",
        )
        assert len(rels) == 1

    def test_startup_products_invalid_type(self) -> None:
        """When products is neither dict nor list (line 80 else branch)."""
        entity_data = {"products": "just a string"}
        rels = extract_implicit_relationships(
            entity_data, "STARTUP", "startup_test",
        )
        assert rels == []

    def test_startup_products_int_type(self) -> None:
        """When products is an int (line 80 else branch)."""
        entity_data = {"products": 42}
        rels = extract_implicit_relationships(
            entity_data, "STARTUP", "startup_test",
        )
        assert rels == []

