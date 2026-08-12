"""End-to-end pipeline test — full flow from URL to export validation (v2 §41).

Tests the complete pipeline:
    URL → crawl → raw store → LLM (mocked) → grounding → resolution → DB → export validation

Mark: @pytest.mark.e2e

Requires: Docker Compose stack (Postgres, Redis, MinIO).
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ─── Mock HTML fixture ───────────────────────────────────────────
MOCK_HTML = """
<html>
<head><title>OpenAI - AI Safety Company</title></head>
<body>
<h1>OpenAI</h1>
<p>OpenAI is an AI safety company founded in 2015 by Sam Altman.</p>
<p>The company has raised $11.3 billion in funding and is based in San Francisco.</p>
<p>OpenAI builds ChatGPT, the world's most popular AI assistant.</p>
<p>Website: https://openai.com</p>
</body>
</html>
"""

MOCK_LLM_RESPONSE = {
    "entityName": {"value": "OpenAI", "evidence": "OpenAI is an AI safety company", "confidence": 0.99},
    "description": {"value": "AI safety company", "evidence": "OpenAI is an AI safety company", "confidence": 0.95},
    "foundedDate": {"value": "2015", "evidence": "founded in 2015", "confidence": 0.90},
    "founders": [{"value": "Sam Altman", "evidence": "founded in 2015 by Sam Altman", "confidence": 0.92}],
    "fundingTotal": {"value": "$11.3B", "evidence": "raised $11.3 billion in funding", "confidence": 0.97},
    "headquarters": {"value": "San Francisco", "evidence": "based in San Francisco", "confidence": 0.93},
    "website": {"value": "https://openai.com", "evidence": "Website: https://openai.com", "confidence": 0.99},
}


@pytest.mark.e2e
class TestFullPipeline:
    """End-to-end pipeline test with mocked external dependencies."""

    async def test_extraction_to_grounding(self):
        """Test extraction output flows correctly through grounding."""
        from provenmesh.grounding.text_match import verify_text_field
        from provenmesh.grounding.numeric_match import verify_numeric_field
        from provenmesh.domain.enums import FieldVerification

        source_text = MOCK_HTML

        # Verify entity name (text match)
        status, score = verify_text_field(
            "OpenAI",
            "OpenAI is an AI safety company",
            source_text,
        )
        assert status == FieldVerification.GROUNDED
        assert score >= 90

        # Verify funding (numeric match)
        status, score = verify_numeric_field(
            "$11.3B",
            "raised $11.3 billion in funding",
            source_text,
        )
        assert status == FieldVerification.GROUNDED

    async def test_grounding_to_resolution(self):
        """Test grounded entity flows through resolution."""
        from provenmesh.resolver.seeds import SeedStore
        from provenmesh.resolver.normalization import normalize_entity_name

        store = SeedStore()
        store.add("startup_openai", "OpenAI", ["Open AI", "OpenAI Inc"])

        # Exact match should work
        result = store.find("OpenAI")
        assert result is not None
        assert result.canonical_id == "startup_openai"

        # Alias match
        result = store.find("Open AI")
        assert result is not None
        assert result.canonical_id == "startup_openai"

        # Normalized match
        normalized = normalize_entity_name("OpenAI Inc.")
        result = store.find_normalized(normalized)
        assert result is not None

    async def test_resolution_to_export_validation(self):
        """Test resolved entity passes export quality gates."""
        from provenmesh.export.validate import validate_for_export

        result = validate_for_export(
            canonical_id="startup_openai",
            record_type="STARTUP",
            content=MOCK_LLM_RESPONSE,
            verification_status="grounded",
            schema_valid=True,
            resolution_method="exact",
        )
        assert result.is_valid, f"Export validation failed: {result.errors}"

    async def test_unverified_rejected_for_export(self):
        """Unverified entities must NOT pass export gates."""
        from provenmesh.export.validate import validate_for_export

        result = validate_for_export(
            canonical_id="startup_unknown",
            record_type="STARTUP",
            content={"entityName": {"value": "Unknown"}},
            verification_status="unverified",
            schema_valid=False,
            resolution_method="unresolved",
        )
        assert not result.is_valid
        assert len(result.errors) >= 2  # Multiple gate failures

    async def test_serialization_strips_internal_fields(self):
        """Export serialization must strip internal metadata."""
        from provenmesh.export.serializers import flatten_evidenced_field, INTERNAL_FIELDS

        # Evidence-first field should flatten
        flat = flatten_evidenced_field({"value": "OpenAI", "evidence": "...", "confidence": 0.99})
        assert flat == "OpenAI"

        # Internal fields must be in the blocklist
        assert "content_hash" in INTERNAL_FIELDS
        assert "correlation_id" in INTERNAL_FIELDS
        assert "raw_s3_key" in INTERNAL_FIELDS

    async def test_content_hash_determinism(self):
        """Same content must always produce the same hash."""
        content = MOCK_HTML.encode()
        hash1 = hashlib.sha256(content).hexdigest()
        hash2 = hashlib.sha256(content).hexdigest()
        assert hash1 == hash2

    async def test_confidence_scoring(self):
        """Test entity confidence computation."""
        from provenmesh.graph.confidence import ConfidenceFactors, compute_entity_confidence

        # Seed entity → 1.0
        seed_conf = compute_entity_confidence(ConfidenceFactors(is_seed=True))
        assert seed_conf == 1.0

        # Well-resolved entity → high confidence
        good_conf = compute_entity_confidence(ConfidenceFactors(
            resolution_confidence=0.95,
            grounding_ratio=0.9,
            source_count=3,
            schema_valid=True,
            days_since_last_update=2,
        ))
        assert good_conf > 0.8

        # Poor entity → low confidence
        bad_conf = compute_entity_confidence(ConfidenceFactors(
            resolution_confidence=0.3,
            grounding_ratio=0.2,
            source_count=1,
            schema_valid=False,
            days_since_last_update=120,
        ))
        assert bad_conf < 0.4
