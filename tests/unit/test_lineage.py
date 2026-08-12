"""Tests for data lineage tracking.

Covers:
    - LineageNode, SourceTrace, FieldLineage, EntityLineage models
    - LineageTracker: field lineage, entity lineage, source extraction
    - Serialization to API response format (to_dict)
    - Edge cases: empty data, missing stages, no conflict resolution
"""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from provenmesh.export.lineage import (
    EntityLineage,
    FieldLineage,
    LineageNode,
    LineageStage,
    LineageStats,
    LineageTracker,
    SourceTrace,
)

NOW = datetime.now(tz=UTC)


def _mock_evidence_record(
    field_name: str = "foundedDate",
    value: str = "2015",
    evidence: str = "founded in 2015",
    source_url: str = "https://crunchbase.com/openai",
    fuzzy_score: float = 95.0,
) -> SimpleNamespace:
    """Mock an EvidenceRecord with required attributes."""
    return SimpleNamespace(
        field_name=field_name,
        extracted_value=value,
        evidence_text=evidence,
        source_url=source_url,
        source_content_hash="abc123",
        raw_s3_key="raw/crunchbase/openai.html",
        fuzzy_score=fuzzy_score,
        verified_at=NOW,
    )


def _mock_hallucination_report(
    trust: float = 0.97,
    recommendation: str = "accept",
    flags: list | None = None,
) -> SimpleNamespace:
    """Mock a HallucinationReport."""
    return SimpleNamespace(
        overall_trust_score=trust,
        recommendation=recommendation,
        flags=flags or [],
    )


def _mock_field_resolution(
    winning_value: str = "2015",
    confidence: float = 0.94,
    method: str = "majority_vote",
    winning_assertions: list | None = None,
    dissenting_assertions: list | None = None,
) -> SimpleNamespace:
    """Mock a FieldResolution from conflict resolver."""
    return SimpleNamespace(
        winning_value=winning_value,
        confidence=confidence,
        resolution_method=method,
        winning_assertions=winning_assertions or [],
        dissenting_assertions=dissenting_assertions or [],
    )


# ─── Model Tests ─────────────────────────────────────────────────

class TestLineageNode:
    def test_passed_above_threshold(self) -> None:
        node = LineageNode(
            stage=LineageStage.GROUNDED,
            timestamp=NOW,
            score=0.95,
        )
        assert node.passed

    def test_failed_below_threshold(self) -> None:
        node = LineageNode(
            stage=LineageStage.GROUNDED,
            timestamp=NOW,
            score=0.3,
        )
        assert not node.passed

    def test_boundary_at_06(self) -> None:
        node = LineageNode(
            stage=LineageStage.GROUNDED,
            timestamp=NOW,
            score=0.6,
        )
        assert node.passed


class TestSourceTrace:
    def test_overall_quality(self) -> None:
        trace = SourceTrace(
            source_url="https://crunchbase.com",
            source_name="crunchbase",
            value="2015",
            evidence_text="founded in 2015",
            grounding_score=0.95,
            trust_score=0.90,
        )
        assert trace.overall_quality == pytest.approx(0.855)

    def test_default_quality(self) -> None:
        trace = SourceTrace(
            source_url="", source_name="", value="",
            evidence_text="",
        )
        assert trace.overall_quality == 0.0


class TestFieldLineage:
    def test_empty_lineage(self) -> None:
        fl = FieldLineage(
            entity_id="e1", field_name="name", final_value="X",
        )
        assert fl.source_count == 0
        assert fl.agreeing_count == 0
        assert not fl.is_contested

    def test_contested_field(self) -> None:
        fl = FieldLineage(
            entity_id="e1",
            field_name="year",
            final_value="2015",
            source_traces=[
                SourceTrace(
                    source_url="a", source_name="a", value="2015",
                    evidence_text="", is_winner=True,
                ),
                SourceTrace(
                    source_url="b", source_name="b", value="2016",
                    evidence_text="", is_dissenter=True,
                ),
            ],
        )
        assert fl.is_contested
        assert fl.source_count == 2
        assert fl.agreeing_count == 1

    def test_to_dict_structure(self) -> None:
        fl = FieldLineage(
            entity_id="e1",
            field_name="year",
            final_value="2015",
            confidence=0.94,
            resolution_method="majority_vote",
            source_traces=[
                SourceTrace(
                    source_url="https://crunchbase.com",
                    source_name="crunchbase",
                    value="2015",
                    evidence_text="founded in 2015",
                    grounding_score=0.95,
                    trust_score=0.97,
                    is_winner=True,
                    fetched_at=NOW,
                ),
            ],
            lineage_chain=[
                LineageNode(
                    stage=LineageStage.GROUNDED,
                    timestamp=NOW,
                    score=0.95,
                ),
            ],
        )
        d = fl.to_dict()
        assert d["field_name"] == "year"
        assert d["final_value"] == "2015"
        assert d["confidence"] == 0.94
        assert d["source_count"] == 1
        assert len(d["sources"]) == 1
        assert d["sources"][0]["status"] == "winner"
        assert len(d["lineage_chain"]) == 1
        assert d["lineage_chain"][0]["stage"] == "grounded"

    def test_to_dict_single_source_status(self) -> None:
        fl = FieldLineage(
            entity_id="e1",
            field_name="name",
            final_value="OpenAI",
            source_traces=[
                SourceTrace(
                    source_url="a", source_name="a",
                    value="OpenAI", evidence_text="",
                    is_winner=False, is_dissenter=False,
                ),
            ],
        )
        d = fl.to_dict()
        assert d["sources"][0]["status"] == "single_source"

    def test_to_dict_none_fetched_at(self) -> None:
        fl = FieldLineage(
            entity_id="e1",
            field_name="name",
            final_value="OpenAI",
            source_traces=[
                SourceTrace(
                    source_url="a", source_name="a",
                    value="OpenAI", evidence_text="",
                    fetched_at=None,
                ),
            ],
        )
        d = fl.to_dict()
        assert d["sources"][0]["fetched_at"] is None


class TestEntityLineage:
    def test_empty_entity(self) -> None:
        el = EntityLineage(entity_id="e1")
        assert el.field_count == 0
        assert not el.has_conflicts

    def test_with_conflicts(self) -> None:
        el = EntityLineage(
            entity_id="e1",
            contested_fields=["funding"],
        )
        assert el.has_conflicts

    def test_to_dict(self) -> None:
        el = EntityLineage(
            entity_id="e1",
            entity_name="OpenAI",
            record_type="STARTUP",
            overall_confidence=0.91,
            total_sources=3,
            field_lineages={
                "name": FieldLineage(
                    entity_id="e1",
                    field_name="name",
                    final_value="OpenAI",
                ),
            },
        )
        d = el.to_dict()
        assert d["entity_id"] == "e1"
        assert d["entity_name"] == "OpenAI"
        assert d["field_count"] == 1
        assert "name" in d["fields"]


class TestLineageStats:
    def test_to_dict(self) -> None:
        stats = LineageStats(
            total_entities=100,
            total_fields=500,
            avg_confidence=0.89,
        )
        d = stats.to_dict()
        assert d["total_entities"] == 100
        assert d["avg_confidence"] == 0.89


# ─── LineageTracker Tests ────────────────────────────────────────

class TestLineageTrackerFieldLineage:
    def test_basic_field_lineage(self) -> None:
        tracker = LineageTracker()
        evidence = [
            _mock_evidence_record("foundedDate", "2015"),
        ]
        lineage = tracker.build_field_lineage(
            entity_id="e1",
            field_name="foundedDate",
            final_value="2015",
            evidence_records=evidence,
        )
        assert lineage.final_value == "2015"
        assert lineage.source_count == 1
        assert len(lineage.lineage_chain) >= 1
        assert lineage.lineage_chain[0].stage == LineageStage.GROUNDED

    def test_with_hallucination_report(self) -> None:
        tracker = LineageTracker()
        evidence = [
            _mock_evidence_record("name", "OpenAI"),
        ]
        report = _mock_hallucination_report(trust=0.85)
        lineage = tracker.build_field_lineage(
            entity_id="e1",
            field_name="name",
            final_value="OpenAI",
            evidence_records=evidence,
            hallucination_report=report,
        )
        assert len(lineage.lineage_chain) >= 2
        hal_node = [
            n for n in lineage.lineage_chain
            if n.stage == LineageStage.HALLUCINATION_CHECKED
        ]
        assert len(hal_node) == 1
        assert hal_node[0].score == 0.85
        # Trust score propagated to traces
        assert lineage.source_traces[0].trust_score == 0.85

    def test_with_hallucination_flags(self) -> None:
        tracker = LineageTracker()
        evidence = [
            _mock_evidence_record("name", "FakeCompany"),
        ]
        flag = SimpleNamespace(
            field_name="name",
            check_type="fabrication",
            severity="critical",
            message="Evidence fabricated",
        )
        report = _mock_hallucination_report(
            trust=0.50, flags=[flag],
        )
        lineage = tracker.build_field_lineage(
            entity_id="e1",
            field_name="name",
            final_value="FakeCompany",
            evidence_records=evidence,
            hallucination_report=report,
        )
        assert len(lineage.hallucination_flags) == 1
        assert lineage.hallucination_flags[0]["severity"] == "critical"

    def test_wildcard_flags_included(self) -> None:
        """Flags with field_name='*' apply to all fields."""
        tracker = LineageTracker()
        flag = SimpleNamespace(
            field_name="*",
            check_type="uniformity",
            severity="warning",
            message="All same confidence",
        )
        report = _mock_hallucination_report(
            trust=0.80, flags=[flag],
        )
        lineage = tracker.build_field_lineage(
            entity_id="e1",
            field_name="name",
            final_value="OpenAI",
            hallucination_report=report,
        )
        assert len(lineage.hallucination_flags) == 1

    def test_with_conflict_resolution(self) -> None:
        tracker = LineageTracker()
        evidence = [
            _mock_evidence_record(
                "year", "2015",
                source_url="https://crunchbase.com/openai",
            ),
            _mock_evidence_record(
                "year", "2016",
                source_url="https://venturebeat.com/openai",
            ),
        ]
        winner = SimpleNamespace(
            source_url="https://crunchbase.com/openai",
        )
        dissenter = SimpleNamespace(
            source_url="https://venturebeat.com/openai",
        )
        resolution = _mock_field_resolution(
            winning_value="2015",
            confidence=0.94,
            method="majority_vote",
            winning_assertions=[winner],
            dissenting_assertions=[dissenter],
        )
        lineage = tracker.build_field_lineage(
            entity_id="e1",
            field_name="year",
            final_value="2015",
            evidence_records=evidence,
            conflict_resolution=resolution,
        )
        assert lineage.confidence == 0.94
        assert lineage.resolution_method == "majority_vote"
        assert lineage.source_traces[0].is_winner
        assert lineage.source_traces[1].is_dissenter

    def test_no_conflict_uses_best_quality(self) -> None:
        tracker = LineageTracker()
        evidence = [
            _mock_evidence_record(
                "name", "OpenAI", fuzzy_score=0.95,
            ),
        ]
        lineage = tracker.build_field_lineage(
            entity_id="e1",
            field_name="name",
            final_value="OpenAI",
            evidence_records=evidence,
        )
        assert lineage.resolution_method == "single_source"
        assert lineage.confidence > 0.0

    def test_no_evidence_records(self) -> None:
        tracker = LineageTracker()
        lineage = tracker.build_field_lineage(
            entity_id="e1",
            field_name="name",
            final_value="OpenAI",
        )
        assert lineage.source_count == 0
        assert lineage.confidence == 0.0

    def test_evidence_for_different_field_ignored(self) -> None:
        tracker = LineageTracker()
        evidence = [
            _mock_evidence_record("otherField", "irrelevant"),
        ]
        lineage = tracker.build_field_lineage(
            entity_id="e1",
            field_name="name",
            final_value="OpenAI",
            evidence_records=evidence,
        )
        assert lineage.source_count == 0

    def test_grounding_score_normalized(self) -> None:
        """Scores > 1 (0-100 scale) get normalized to 0-1."""
        tracker = LineageTracker()
        evidence = [
            _mock_evidence_record("name", "OpenAI", fuzzy_score=95.0),
        ]
        lineage = tracker.build_field_lineage(
            entity_id="e1",
            field_name="name",
            final_value="OpenAI",
            evidence_records=evidence,
        )
        grounding_node = lineage.lineage_chain[0]
        assert grounding_node.score == 0.95


class TestLineageTrackerEntityLineage:
    def test_basic_entity_lineage(self) -> None:
        tracker = LineageTracker()
        fl1 = FieldLineage(
            entity_id="e1",
            field_name="name",
            final_value="OpenAI",
            confidence=0.95,
            source_traces=[
                SourceTrace(
                    source_url="https://crunchbase.com",
                    source_name="crunchbase",
                    value="OpenAI",
                    evidence_text="",
                ),
            ],
        )
        fl2 = FieldLineage(
            entity_id="e1",
            field_name="year",
            final_value="2015",
            confidence=0.90,
            source_traces=[
                SourceTrace(
                    source_url="https://techcrunch.com",
                    source_name="techcrunch",
                    value="2015",
                    evidence_text="",
                    is_dissenter=True,
                ),
            ],
        )
        entity = tracker.build_entity_lineage(
            entity_id="e1",
            entity_name="OpenAI",
            record_type="STARTUP",
            field_lineages={"name": fl1, "year": fl2},
        )
        assert entity.field_count == 2
        assert entity.total_sources == 2
        assert entity.overall_confidence == pytest.approx(0.925)
        assert "year" in entity.contested_fields

    def test_empty_entity(self) -> None:
        tracker = LineageTracker()
        entity = tracker.build_entity_lineage(entity_id="e1")
        assert entity.field_count == 0
        assert entity.overall_confidence == 0.0
        assert entity.total_sources == 0


class TestSourceNameExtraction:
    def test_crunchbase(self) -> None:
        assert (
            LineageTracker._extract_source_name(
                "https://www.crunchbase.com/org/openai",
            )
            == "crunchbase"
        )

    def test_techcrunch(self) -> None:
        assert (
            LineageTracker._extract_source_name(
                "https://techcrunch.com/2024/01/openai",
            )
            == "techcrunch"
        )

    def test_empty_url(self) -> None:
        assert LineageTracker._extract_source_name("") == ""

    def test_no_www(self) -> None:
        assert (
            LineageTracker._extract_source_name(
                "https://linkedin.com/company/openai",
            )
            == "linkedin"
        )

    def test_invalid_url(self) -> None:
        result = LineageTracker._extract_source_name("not-a-url")
        assert isinstance(result, str)


class TestLineageStageEnum:
    def test_all_stages_exist(self) -> None:
        assert LineageStage.CRAWLED == "crawled"
        assert LineageStage.EXTRACTED == "extracted"
        assert LineageStage.GROUNDED == "grounded"
        assert LineageStage.HALLUCINATION_CHECKED == "hallucination_checked"
        assert LineageStage.RESOLVED == "resolved"
        assert LineageStage.CONFLICT_RESOLVED == "conflict_resolved"
        assert LineageStage.EXPORTED == "exported"
