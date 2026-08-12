"""Grounding evidence builder — creates evidence records from verification results (v2 §29)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from provenmesh.domain.enums import FieldVerification
from provenmesh.domain.evidence import EvidenceRecord


def build_evidence_record(
    entity_id: str,
    field_name: str,
    extracted_value: str,
    evidence_text: str,
    source_url: str,
    content_hash: str,
    raw_s3_key: str,
    verification_status: FieldVerification,
    fuzzy_score: float,
    correlation_id: str = "",
) -> EvidenceRecord:
    """Create an evidence record for a single field verification."""
    return EvidenceRecord(
        evidence_id=str(uuid.uuid4()),
        entity_id=entity_id,
        field_name=field_name,
        extracted_value=str(extracted_value)[:500],
        evidence_text=str(evidence_text)[:1000],
        source_url=source_url,
        source_content_hash=content_hash,
        raw_s3_key=raw_s3_key,
        verification_status=verification_status,
        fuzzy_score=fuzzy_score,
        verified_at=datetime.now(UTC) if verification_status == FieldVerification.GROUNDED else None,  # noqa: E501
        correlation_id=correlation_id,
    )


def build_evidence_chain(
    entity_id: str,
    field_results: list[tuple[str, str, str, FieldVerification, float]],
    source_url: str,
    content_hash: str,
    raw_s3_key: str,
    correlation_id: str = "",
) -> list[EvidenceRecord]:
    """Build a complete evidence chain for all fields in a record.

    Args:
        field_results: List of (field_name, extracted_value, evidence_text, status, score)
    """
    records: list[EvidenceRecord] = []
    for field_name, value, evidence, status, score in field_results:
        record = build_evidence_record(
            entity_id=entity_id,
            field_name=field_name,
            extracted_value=value,
            evidence_text=evidence,
            source_url=source_url,
            content_hash=content_hash,
            raw_s3_key=raw_s3_key,
            verification_status=status,
            fuzzy_score=score,
            correlation_id=correlation_id,
        )
        records.append(record)
    return records
