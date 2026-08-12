"""Tests for graph/models.py — ORM model definitions and table structure."""
from __future__ import annotations

from provenmesh.graph.models import (
    Base,
    CrawlItemRecord,
    EntityRecord,
    EvidenceRow,
    ExportRunRecord,
    RelationshipRecord,
    ReviewItemRecord,
)


class TestEntityRecord:
    def test_tablename(self) -> None:
        assert EntityRecord.__tablename__ == "entities"

    def test_columns_exist(self) -> None:
        cols = {c.name for c in EntityRecord.__table__.columns}
        assert "id" in cols
        assert "canonical_id" in cols
        assert "record_type" in cols
        assert "entity_name" in cols
        assert "normalized_name" in cols
        assert "content" in cols
        assert "resolution_method" in cols
        assert "verification_status" in cols
        assert "embedding" in cols
        assert "source_url" in cols
        assert "created_at" in cols
        assert "updated_at" in cols

    def test_constraints(self) -> None:
        # Check that canonical_id is unique
        col = EntityRecord.__table__.columns["canonical_id"]
        assert col.unique is True


class TestRelationshipRecord:
    def test_tablename(self) -> None:
        assert RelationshipRecord.__tablename__ == "relationships"

    def test_columns(self) -> None:
        cols = {c.name for c in RelationshipRecord.__table__.columns}
        assert "source_id" in cols
        assert "target_id" in cols
        assert "relation_type" in cols
        assert "confidence" in cols
        assert "evidence_text" in cols


class TestEvidenceRow:
    def test_tablename(self) -> None:
        assert EvidenceRow.__tablename__ == "evidence_records"

    def test_columns(self) -> None:
        cols = {c.name for c in EvidenceRow.__table__.columns}
        assert "entity_id" in cols
        assert "field_name" in cols
        assert "fuzzy_score" in cols
        assert "verified_at" in cols


class TestCrawlItemRecord:
    def test_tablename(self) -> None:
        assert CrawlItemRecord.__tablename__ == "crawl_items"

    def test_state_column(self) -> None:
        cols = {c.name for c in CrawlItemRecord.__table__.columns}
        assert "processing_state" in cols
        assert "attempt_count" in cols
        assert "fetch_tier" in cols


class TestReviewItemRecord:
    def test_tablename(self) -> None:
        assert ReviewItemRecord.__tablename__ == "review_items"

    def test_columns(self) -> None:
        cols = {c.name for c in ReviewItemRecord.__table__.columns}
        assert "extracted_name" in cols
        assert "candidate_canonical_id" in cols
        assert "status" in cols


class TestExportRunRecord:
    def test_tablename(self) -> None:
        assert ExportRunRecord.__tablename__ == "export_runs"

    def test_columns(self) -> None:
        cols = {c.name for c in ExportRunRecord.__table__.columns}
        assert "run_id" in cols
        assert "records_exported" in cols
        assert "records_failed" in cols


class TestBase:
    def test_declarative_base(self) -> None:
        assert hasattr(Base, "metadata")
        # Verify all tables are registered
        table_names = set(Base.metadata.tables.keys())
        assert "entities" in table_names
        assert "relationships" in table_names
        assert "evidence_records" in table_names
        assert "crawl_items" in table_names
        assert "review_items" in table_names
        assert "export_runs" in table_names
