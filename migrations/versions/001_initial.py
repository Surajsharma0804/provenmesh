"""Initial schema — all ProvenMesh tables.

Revision ID: 001_initial
Revises:
Create Date: 2026-08-12
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Enable pgvector extension
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # Entities table
    op.create_table(
        "entities",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("canonical_id", sa.String(255), nullable=False),
        sa.Column("record_type", sa.String(50), nullable=False),
        sa.Column("entity_name", sa.String(500), nullable=False),
        sa.Column("normalized_name", sa.String(500), nullable=False),
        sa.Column("content", JSONB(), nullable=False, server_default="{}"),
        sa.Column("resolution_method", sa.String(50), server_default="unresolved"),
        sa.Column("resolution_confidence", sa.Float(), server_default="0.0"),
        sa.Column("source_count", sa.Integer(), server_default="1"),
        sa.Column("is_seed", sa.Boolean(), server_default="false"),
        sa.Column("verification_status", sa.String(50), server_default="unverified"),
        sa.Column("grounding_ratio", sa.Float(), server_default="0.0"),
        sa.Column("schema_valid", sa.Boolean(), server_default="false"),
        sa.Column("source_url", sa.Text(), server_default=""),
        sa.Column("content_hash", sa.String(64), server_default=""),
        sa.Column("raw_s3_key", sa.Text(), server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("exported_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("canonical_id"),
    )
    op.create_index("idx_entities_type_verification", "entities", ["record_type", "verification_status"])
    op.create_index("idx_entities_name_type", "entities", ["normalized_name", "record_type"])

    # Add pgvector column separately (Alembic doesn't handle Vector type natively)
    op.execute("ALTER TABLE entities ADD COLUMN embedding vector(384)")

    # Relationships table
    op.create_table(
        "relationships",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("source_id", sa.String(255), nullable=False),
        sa.Column("target_id", sa.String(255), nullable=False),
        sa.Column("relation_type", sa.String(50), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("source_url", sa.Text(), server_default=""),
        sa.Column("source_content_hash", sa.String(64), server_default=""),
        sa.Column("evidence_text", sa.Text(), server_default=""),
        sa.Column("collected_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source_id", "target_id", "relation_type", "source_url", name="uq_relationship_edge"),
    )
    op.create_index("idx_rel_source", "relationships", ["source_id"])
    op.create_index("idx_rel_target", "relationships", ["target_id"])
    op.create_index("idx_rel_type", "relationships", ["relation_type"])

    # Evidence records table
    op.create_table(
        "evidence_records",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("entity_id", sa.String(255), nullable=False),
        sa.Column("field_name", sa.String(255), nullable=False),
        sa.Column("extracted_value", sa.Text(), server_default=""),
        sa.Column("evidence_text", sa.Text(), server_default=""),
        sa.Column("source_url", sa.Text(), server_default=""),
        sa.Column("source_content_hash", sa.String(64), server_default=""),
        sa.Column("raw_s3_key", sa.Text(), server_default=""),
        sa.Column("verification_status", sa.String(50), server_default="UNVERIFIED"),
        sa.Column("fuzzy_score", sa.Float(), server_default="0.0"),
        sa.Column("correlation_id", sa.String(36), server_default=""),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_evidence_entity_field", "evidence_records", ["entity_id", "field_name"])

    # Crawl items table
    op.create_table(
        "crawl_items",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("source_name", sa.String(100), nullable=False),
        sa.Column("record_type", sa.String(50), nullable=False),
        sa.Column("processing_state", sa.String(50), server_default="DISCOVERED"),
        sa.Column("content_hash", sa.String(64), server_default=""),
        sa.Column("raw_s3_key", sa.Text(), server_default=""),
        sa.Column("fetch_tier", sa.Integer(), server_default="1"),
        sa.Column("status_code", sa.Integer(), server_default="0"),
        sa.Column("attempt_count", sa.Integer(), server_default="0"),
        sa.Column("last_error", sa.Text(), server_default=""),
        sa.Column("correlation_id", sa.String(36), server_default=""),
        sa.Column("canonical_id", sa.String(255), server_default=""),
        sa.Column("discovered_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("extracted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("exported_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("url", "source_name", name="uq_crawl_item_url_source"),
    )
    op.create_index("idx_crawl_state", "crawl_items", ["processing_state"])
    op.create_index("idx_crawl_source_type", "crawl_items", ["source_name", "record_type"])

    # Review items table
    op.create_table(
        "review_items",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("extracted_name", sa.String(500), nullable=False),
        sa.Column("candidate_canonical_id", sa.String(255), server_default=""),
        sa.Column("candidate_name", sa.String(500), server_default=""),
        sa.Column("record_type", sa.String(50), nullable=False),
        sa.Column("similarity_score", sa.Float(), server_default="0.0"),
        sa.Column("resolution_method", sa.String(50), server_default=""),
        sa.Column("evidence_summary", sa.Text(), server_default=""),
        sa.Column("source_url", sa.Text(), server_default=""),
        sa.Column("status", sa.String(50), server_default="needs_review"),
        sa.Column("reviewer", sa.String(100), server_default=""),
        sa.Column("decision", sa.String(50), server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )

    # Export runs table
    op.create_table(
        "export_runs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("run_id", sa.String(36), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(50), server_default="running"),
        sa.Column("records_exported", sa.Integer(), server_default="0"),
        sa.Column("records_skipped", sa.Integer(), server_default="0"),
        sa.Column("records_failed", sa.Integer(), server_default="0"),
        sa.Column("error_message", sa.Text(), server_default=""),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_id"),
    )


def downgrade() -> None:
    op.drop_table("export_runs")
    op.drop_table("review_items")
    op.drop_table("crawl_items")
    op.drop_table("evidence_records")
    op.drop_table("relationships")
    op.drop_table("entities")
    op.execute("DROP EXTENSION IF EXISTS vector")
