"""Unit tests for domain entities — evidence-first field validation."""

from __future__ import annotations

import pytest

from provenmesh.domain.entities import (
    ENTITY_TYPE_MAP,
    EvidencedField,
    JobEntity,
    NewsSignal,
    PaperEntity,
    ProductEntity,
    SourceInfo,
    StartupEntity,
    create_entity,
)
from provenmesh.domain.enums import ProcessingState, RecordType, VerificationStatus


class TestEvidencedField:
    """Tests for the evidence-first field model."""

    def test_default_field(self) -> None:
        field = EvidencedField()
        assert field.value is None
        assert field.evidence is None
        assert field.confidence == 0.0

    def test_populated_field(self) -> None:
        field = EvidencedField(
            value="OpenAI",
            evidence="OpenAI is an AI research company",
            confidence=0.95,
        )
        assert field.value == "OpenAI"
        assert field.confidence == 0.95
        assert "research company" in field.evidence

    def test_field_is_frozen(self) -> None:
        field = EvidencedField(value="test")
        with pytest.raises(Exception):
            field.value = "modified"  # type: ignore

    def test_confidence_bounds(self) -> None:
        with pytest.raises(Exception):
            EvidencedField(value="test", confidence=1.5)
        with pytest.raises(Exception):
            EvidencedField(value="test", confidence=-0.1)


class TestEntityCreation:
    """Tests for entity type creation and registry."""

    def test_startup_entity(self) -> None:
        source = SourceInfo(url="https://example.com/startup")
        entity = StartupEntity(source=source)
        assert entity.record_type == "STARTUP"
        assert entity.schema_version == "1.0"

    def test_product_entity(self) -> None:
        source = SourceInfo(url="https://example.com/product")
        entity = ProductEntity(source=source)
        assert entity.record_type == "PRODUCT"

    def test_paper_entity(self) -> None:
        source = SourceInfo(url="https://arxiv.org/abs/2301.00001")
        entity = PaperEntity(source=source)
        assert entity.record_type == "PAPER"

    def test_job_entity(self) -> None:
        source = SourceInfo(url="https://example.com/job")
        entity = JobEntity(source=source)
        assert entity.record_type == "JOB"

    def test_news_signal(self) -> None:
        source = SourceInfo(url="https://example.com/news")
        entity = NewsSignal(source=source)
        assert entity.record_type == "NEWS_SIGNAL"

    def test_create_entity_factory(self) -> None:
        source = SourceInfo(url="https://example.com")
        entity = create_entity("STARTUP", source=source)
        assert isinstance(entity, StartupEntity)

    def test_create_entity_unknown_type(self) -> None:
        with pytest.raises(ValueError, match="Unknown record type"):
            create_entity("INVALID", source=SourceInfo(url="https://example.com"))

    def test_entity_type_map_complete(self) -> None:
        expected_types = {"STARTUP", "PRODUCT", "PAPER", "JOB", "NEWS_SIGNAL"}
        assert set(ENTITY_TYPE_MAP.keys()) == expected_types


class TestEnums:
    """Tests for domain enumerations."""

    def test_record_types(self) -> None:
        assert len(RecordType) == 5
        assert RecordType.STARTUP == "STARTUP"

    def test_processing_states(self) -> None:
        # All happy-path states should exist
        happy_path = [
            "DISCOVERED", "QUEUED", "FETCHING", "FETCHED",
            "EXTRACTED", "GROUNDED", "RESOLVED", "EXPORTED",
        ]
        state_values = [s.value for s in ProcessingState]
        for state in happy_path:
            assert state in state_values

    def test_verification_status(self) -> None:
        assert VerificationStatus.GROUNDED == "grounded"
        assert VerificationStatus.REJECTED == "rejected"
