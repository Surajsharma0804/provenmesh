"""Graph relationships — relationship extraction and management (v2 §26).

Handles creation, validation, and deduplication of inter-entity relationships.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from provenmesh.domain.enums import RelationType
from provenmesh.graph.models import RelationshipRecord
from provenmesh.observability.logging import get_logger

logger = get_logger(__name__)

# Valid relationship types and their expected source/target types
VALID_RELATIONSHIPS: dict[str, dict[str, list[str]]] = {
    "FOUNDED_BY": {"source": ["STARTUP"], "target": ["STARTUP", "PRODUCT"]},
    "BUILDS_PRODUCT": {"source": ["STARTUP"], "target": ["PRODUCT"]},
    "PUBLISHED_PAPER": {"source": ["STARTUP"], "target": ["PAPER"]},
    "CITES": {"source": ["PAPER"], "target": ["PAPER"]},
    "WORKS_AT": {"source": ["JOB"], "target": ["STARTUP"]},
}


def validate_relationship(
    source_type: str,
    target_type: str,
    relation_type: str,
) -> bool:
    """Validate that a relationship type is valid for the given source/target types."""
    if relation_type not in VALID_RELATIONSHIPS:
        return False
    spec = VALID_RELATIONSHIPS[relation_type]
    return source_type in spec.get("source", []) or target_type in spec.get("target", [])


def build_relationship_record(
    source_id: str,
    target_id: str,
    relation_type: str,
    confidence: float,
    source_url: str = "",
    content_hash: str = "",
    evidence_text: str = "",
) -> RelationshipRecord:
    """Create a relationship record with validation."""
    return RelationshipRecord(
        source_id=source_id,
        target_id=target_id,
        relation_type=relation_type,
        confidence=min(max(confidence, 0.0), 1.0),
        source_url=source_url,
        source_content_hash=content_hash,
        evidence_text=evidence_text[:1000],
    )


def extract_implicit_relationships(
    entity_data: dict[str, Any],
    record_type: str,
    canonical_id: str,
) -> list[dict[str, Any]]:
    """Extract implicit relationships from entity fields.

    Examples:
        - Startup.products → BUILDS_PRODUCT edges
        - Paper.citations → CITES edges
        - Job.company → WORKS_AT edges
    """
    relationships: list[dict[str, Any]] = []

    if record_type == "STARTUP":
        # Products built by this startup
        products = entity_data.get("products", {})
        if isinstance(products, dict):
            product_list = products.get("value", [])
        elif isinstance(products, list):
            product_list = products
        else:
            product_list = []

        for product in product_list:
            name = product if isinstance(product, str) else product.get("value", "")
            if name:
                relationships.append({
                    "source": canonical_id,
                    "target": name,
                    "type": "BUILDS_PRODUCT",
                    "confidence": 0.8,
                    "evidence": f"Product of {canonical_id}",
                })

    elif record_type == "JOB":
        # Company offering this job
        company = entity_data.get("company", {})
        company_name = ""
        if isinstance(company, dict):
            company_name = company.get("value", "")
        elif isinstance(company, str):
            company_name = company

        if company_name:
            relationships.append({
                "source": canonical_id,
                "target": company_name,
                "type": "WORKS_AT",
                "confidence": 0.95,
                "evidence": f"Job at {company_name}",
            })

    return relationships
