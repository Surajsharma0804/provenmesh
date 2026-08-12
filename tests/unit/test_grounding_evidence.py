"""Tests for grounding/evidence.py — evidence record building."""
from __future__ import annotations

from provenmesh.domain.enums import FieldVerification
from provenmesh.grounding.evidence import build_evidence_chain, build_evidence_record


class TestBuildEvidenceRecord:
    def test_grounded_record(self) -> None:
        record = build_evidence_record(
            entity_id="startup_openai",
            field_name="description",
            extracted_value="AI research company",
            evidence_text="OpenAI is an AI research company",
            source_url="https://example.com",
            content_hash="abc123",
            raw_s3_key="raw/crunchbase/2026/08/12/abc123/payload.html",
            verification_status=FieldVerification.GROUNDED,
            fuzzy_score=0.95,
            correlation_id="cid-123",
        )
        assert record.entity_id == "startup_openai"
        assert record.field_name == "description"
        assert record.fuzzy_score == 0.95
        assert record.verified_at is not None
        assert record.correlation_id == "cid-123"

    def test_unverified_record_no_timestamp(self) -> None:
        record = build_evidence_record(
            entity_id="e1", field_name="website",
            extracted_value="https://test.com",
            evidence_text="", source_url="u",
            content_hash="h", raw_s3_key="k",
            verification_status=FieldVerification.UNVERIFIED,
            fuzzy_score=0.0,
        )
        assert record.verified_at is None

    def test_truncation(self) -> None:
        long_value = "x" * 1000
        long_evidence = "y" * 2000
        record = build_evidence_record(
            entity_id="e1", field_name="f",
            extracted_value=long_value,
            evidence_text=long_evidence,
            source_url="u", content_hash="h",
            raw_s3_key="k",
            verification_status=FieldVerification.GROUNDED,
            fuzzy_score=0.5,
        )
        assert len(record.extracted_value) == 500
        assert len(record.evidence_text) == 1000


class TestBuildEvidenceChain:
    def test_multiple_fields(self) -> None:
        field_results = [
            ("name", "OpenAI", "OpenAI is", FieldVerification.GROUNDED, 0.99),
            ("website", "https://openai.com", "", FieldVerification.UNVERIFIED, 0.0),
            ("founded", "2015", "founded in 2015", FieldVerification.GROUNDED, 0.95),
        ]
        chain = build_evidence_chain(
            entity_id="startup_openai",
            field_results=field_results,
            source_url="https://example.com",
            content_hash="hash1",
            raw_s3_key="key1",
            correlation_id="cid",
        )
        assert len(chain) == 3
        assert chain[0].field_name == "name"
        assert chain[1].field_name == "website"
        assert chain[2].field_name == "founded"

    def test_empty_results(self) -> None:
        chain = build_evidence_chain(
            entity_id="e1", field_results=[],
            source_url="u", content_hash="h",
            raw_s3_key="k",
        )
        assert chain == []


class TestProvenanceChain:
    def test_grounding_ratio_with_data(self) -> None:
        from provenmesh.domain.evidence import ProvenanceChain
        chain = ProvenanceChain(
            entity_id="e1", record_type="STARTUP",
            grounded_field_count=3, total_field_count=4,
        )
        assert chain.grounding_ratio == 0.75

    def test_grounding_ratio_zero_total(self) -> None:
        from provenmesh.domain.evidence import ProvenanceChain
        chain = ProvenanceChain(
            entity_id="e1", record_type="STARTUP",
            grounded_field_count=0, total_field_count=0,
        )
        assert chain.grounding_ratio == 0.0

    def test_grounding_ratio_all_grounded(self) -> None:
        from provenmesh.domain.evidence import ProvenanceChain
        chain = ProvenanceChain(
            entity_id="e1", record_type="STARTUP",
            grounded_field_count=5, total_field_count=5,
        )
        assert chain.grounding_ratio == 1.0

