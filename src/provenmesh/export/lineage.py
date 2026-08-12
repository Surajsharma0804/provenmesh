"""Data Lineage API — trace any value back to its source evidence.

This is the feature that makes ProvenMesh live up to its name: every
single exported value is PROVABLE. Click any cell in the Google Sheet
and trace it through:

    Exported Value → Conflict Resolution → Hallucination Check
    → Grounding Verification → LLM Extraction → Raw HTML → Source URL

Endpoints:
    GET /api/v1/lineage/{entity_id}
        Full provenance chain for an entity

    GET /api/v1/lineage/{entity_id}/{field_name}
        Single field trace with all source assertions

    GET /api/v1/lineage/stats
        Pipeline-wide lineage statistics
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum

from provenmesh.observability.logging import get_logger

logger = get_logger(__name__)


class LineageStage(StrEnum):
    """Pipeline stages in the lineage chain."""

    CRAWLED = "crawled"
    EXTRACTED = "extracted"
    GROUNDED = "grounded"
    HALLUCINATION_CHECKED = "hallucination_checked"
    RESOLVED = "resolved"
    CONFLICT_RESOLVED = "conflict_resolved"
    EXPORTED = "exported"


@dataclass
class LineageNode:
    """A single node in the lineage chain.

    Represents one pipeline stage's contribution to the final value.
    """

    stage: LineageStage
    timestamp: datetime
    input_value: str = ""
    output_value: str = ""
    score: float = 0.0
    metadata: dict = field(default_factory=dict)

    @property
    def passed(self) -> bool:
        return self.score >= 0.6


@dataclass
class SourceTrace:
    """Complete trace of a field value back to a specific source."""

    source_url: str
    source_name: str
    value: str
    evidence_text: str
    raw_s3_key: str = ""
    content_hash: str = ""
    fetched_at: datetime | None = None

    # Quality scores at each stage
    grounding_score: float = 0.0
    trust_score: float = 1.0
    llm_confidence: float = 0.0

    # Conflict resolution outcome for this source
    is_winner: bool = False
    is_dissenter: bool = False

    @property
    def overall_quality(self) -> float:
        return self.grounding_score * self.trust_score


@dataclass
class FieldLineage:
    """Complete lineage for a single field across all sources."""

    entity_id: str
    field_name: str
    final_value: str
    confidence: float = 0.0
    resolution_method: str = ""

    # All source traces for this field
    source_traces: list[SourceTrace] = field(default_factory=list)

    # Pipeline stages this value passed through
    lineage_chain: list[LineageNode] = field(default_factory=list)

    # Hallucination flags (if any)
    hallucination_flags: list[dict] = field(default_factory=list)

    @property
    def source_count(self) -> int:
        return len(self.source_traces)

    @property
    def agreeing_count(self) -> int:
        return sum(1 for s in self.source_traces if s.is_winner)

    @property
    def is_contested(self) -> bool:
        return any(s.is_dissenter for s in self.source_traces)

    def to_dict(self) -> dict:
        """Serialize to API response format."""
        return {
            "entity_id": self.entity_id,
            "field_name": self.field_name,
            "final_value": self.final_value,
            "confidence": round(self.confidence, 4),
            "resolution_method": self.resolution_method,
            "source_count": self.source_count,
            "is_contested": self.is_contested,
            "sources": [
                {
                    "source_url": s.source_url,
                    "source_name": s.source_name,
                    "value": s.value,
                    "evidence_text": s.evidence_text,
                    "grounding_score": round(s.grounding_score, 3),
                    "trust_score": round(s.trust_score, 3),
                    "llm_confidence": round(s.llm_confidence, 3),
                    "overall_quality": round(s.overall_quality, 3),
                    "status": (
                        "winner" if s.is_winner
                        else "dissenter" if s.is_dissenter
                        else "single_source"
                    ),
                    "fetched_at": (
                        s.fetched_at.isoformat() if s.fetched_at else None
                    ),
                    "raw_s3_key": s.raw_s3_key,
                }
                for s in self.source_traces
            ],
            "lineage_chain": [
                {
                    "stage": node.stage.value,
                    "passed": node.passed,
                    "score": round(node.score, 3),
                    "timestamp": node.timestamp.isoformat(),
                    "metadata": node.metadata,
                }
                for node in self.lineage_chain
            ],
            "hallucination_flags": self.hallucination_flags,
        }


@dataclass
class EntityLineage:
    """Complete lineage for an entire entity across all fields."""

    entity_id: str
    entity_name: str = ""
    record_type: str = ""
    canonical_id: str = ""
    field_lineages: dict[str, FieldLineage] = field(default_factory=dict)
    overall_confidence: float = 0.0
    total_sources: int = 0
    contested_fields: list[str] = field(default_factory=list)
    created_at: datetime = field(
        default_factory=lambda: datetime.now(tz=UTC),
    )

    @property
    def field_count(self) -> int:
        return len(self.field_lineages)

    @property
    def has_conflicts(self) -> bool:
        return len(self.contested_fields) > 0

    def to_dict(self) -> dict:
        """Serialize to API response format."""
        return {
            "entity_id": self.entity_id,
            "entity_name": self.entity_name,
            "record_type": self.record_type,
            "canonical_id": self.canonical_id,
            "overall_confidence": round(self.overall_confidence, 4),
            "total_sources": self.total_sources,
            "field_count": self.field_count,
            "has_conflicts": self.has_conflicts,
            "contested_fields": self.contested_fields,
            "fields": {
                name: lineage.to_dict()
                for name, lineage in self.field_lineages.items()
            },
        }


@dataclass
class LineageStats:
    """Pipeline-wide lineage statistics."""

    total_entities: int = 0
    total_fields: int = 0
    total_sources: int = 0
    avg_confidence: float = 0.0
    avg_sources_per_field: float = 0.0
    contested_field_ratio: float = 0.0
    hallucination_flag_rate: float = 0.0
    grounding_pass_rate: float = 0.0

    # Top sources by credibility
    top_sources: list[dict] = field(default_factory=list)

    # Most contested fields
    most_contested: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "total_entities": self.total_entities,
            "total_fields": self.total_fields,
            "total_sources": self.total_sources,
            "avg_confidence": round(self.avg_confidence, 4),
            "avg_sources_per_field": round(
                self.avg_sources_per_field, 2,
            ),
            "contested_field_ratio": round(
                self.contested_field_ratio, 4,
            ),
            "hallucination_flag_rate": round(
                self.hallucination_flag_rate, 4,
            ),
            "grounding_pass_rate": round(
                self.grounding_pass_rate, 4,
            ),
            "top_sources": self.top_sources,
            "most_contested": self.most_contested,
        }


class LineageTracker:
    """Builds and queries data lineage chains.

    Assembles FieldLineage objects from evidence records, hallucination
    reports, and conflict resolution reports to create a complete,
    traceable provenance chain.
    """

    def build_field_lineage(
        self,
        entity_id: str,
        field_name: str,
        final_value: str,
        evidence_records: list | None = None,
        hallucination_report: object | None = None,
        conflict_resolution: object | None = None,
    ) -> FieldLineage:
        """Build a complete lineage for a single field.

        Args:
            entity_id: Entity identifier
            field_name: Field name
            final_value: The final exported value
            evidence_records: Grounding evidence records
            hallucination_report: HallucinationReport from detector
            conflict_resolution: FieldResolution from conflict resolver
        """
        lineage = FieldLineage(
            entity_id=entity_id,
            field_name=field_name,
            final_value=final_value,
        )

        now = datetime.now(tz=UTC)

        # Stage 1: Source traces from evidence records
        if evidence_records:
            for rec in evidence_records:
                if hasattr(rec, "field_name") and rec.field_name == field_name:
                    trace = SourceTrace(
                        source_url=getattr(rec, "source_url", ""),
                        source_name=self._extract_source_name(
                            getattr(rec, "source_url", ""),
                        ),
                        value=getattr(rec, "extracted_value", ""),
                        evidence_text=getattr(rec, "evidence_text", ""),
                        raw_s3_key=getattr(rec, "raw_s3_key", ""),
                        content_hash=getattr(
                            rec, "source_content_hash", "",
                        ),
                        grounding_score=getattr(rec, "fuzzy_score", 0.0),
                        llm_confidence=0.0,
                    )
                    lineage.source_traces.append(trace)

                    # Add grounding stage
                    lineage.lineage_chain.append(LineageNode(
                        stage=LineageStage.GROUNDED,
                        timestamp=getattr(rec, "verified_at", None) or now,
                        input_value=trace.value,
                        output_value=trace.value,
                        score=trace.grounding_score / 100.0
                        if trace.grounding_score > 1
                        else trace.grounding_score,
                        metadata={
                            "fuzzy_score": trace.grounding_score,
                            "source_url": trace.source_url,
                        },
                    ))

        # Stage 2: Hallucination check
        if hallucination_report and hasattr(
            hallucination_report, "overall_trust_score",
        ):
            trust = hallucination_report.overall_trust_score
            flags = []
            if hasattr(hallucination_report, "flags"):
                flags = [
                    {
                        "field": f.field_name,
                        "type": f.check_type,
                        "severity": f.severity,
                        "message": f.message,
                    }
                    for f in hallucination_report.flags
                    if f.field_name == field_name
                    or f.field_name == "*"
                ]

            lineage.hallucination_flags = flags
            lineage.lineage_chain.append(LineageNode(
                stage=LineageStage.HALLUCINATION_CHECKED,
                timestamp=now,
                score=trust,
                metadata={
                    "trust_score": trust,
                    "flags": len(flags),
                    "recommendation": getattr(
                        hallucination_report, "recommendation", "",
                    ),
                },
            ))

            # Update source traces with trust scores
            for trace in lineage.source_traces:
                trace.trust_score = trust

        # Stage 3: Conflict resolution
        if conflict_resolution and hasattr(
            conflict_resolution, "winning_value",
        ):
            lineage.confidence = getattr(
                conflict_resolution, "confidence", 0.0,
            )
            lineage.resolution_method = getattr(
                conflict_resolution, "resolution_method", "",
            )

            # Mark winners and dissenters
            winning_urls = {
                a.source_url
                for a in getattr(
                    conflict_resolution, "winning_assertions", [],
                )
            }
            dissenting_urls = {
                a.source_url
                for a in getattr(
                    conflict_resolution, "dissenting_assertions", [],
                )
            }

            for trace in lineage.source_traces:
                trace.is_winner = trace.source_url in winning_urls
                trace.is_dissenter = trace.source_url in dissenting_urls

            lineage.lineage_chain.append(LineageNode(
                stage=LineageStage.CONFLICT_RESOLVED,
                timestamp=now,
                input_value=final_value,
                output_value=final_value,
                score=lineage.confidence,
                metadata={
                    "method": lineage.resolution_method,
                    "agreeing": len(winning_urls),
                    "dissenting": len(dissenting_urls),
                },
            ))

        # If no conflict resolution, set confidence from grounding
        if not conflict_resolution and lineage.source_traces:
            best = max(
                lineage.source_traces,
                key=lambda s: s.overall_quality,
            )
            lineage.confidence = best.overall_quality
            lineage.resolution_method = "single_source"

        return lineage

    def build_entity_lineage(
        self,
        entity_id: str,
        entity_name: str = "",
        record_type: str = "",
        canonical_id: str = "",
        field_lineages: dict[str, FieldLineage] | None = None,
    ) -> EntityLineage:
        """Assemble a full entity lineage from field lineages."""
        field_lineages = field_lineages or {}

        # Calculate aggregates
        all_sources: set[str] = set()
        contested: list[str] = []
        confidences: list[float] = []

        for name, fl in field_lineages.items():
            for trace in fl.source_traces:
                all_sources.add(trace.source_url)
            if fl.is_contested:
                contested.append(name)
            confidences.append(fl.confidence)

        return EntityLineage(
            entity_id=entity_id,
            entity_name=entity_name,
            record_type=record_type,
            canonical_id=canonical_id,
            field_lineages=field_lineages,
            overall_confidence=(
                sum(confidences) / len(confidences)
                if confidences else 0.0
            ),
            total_sources=len(all_sources),
            contested_fields=contested,
        )

    @staticmethod
    def _extract_source_name(url: str) -> str:
        """Extract a human-readable source name from a URL.

        https://www.crunchbase.com/org/openai -> crunchbase
        """
        if not url:
            return ""
        try:
            from urllib.parse import urlparse
            host = urlparse(url).hostname or ""
            # Remove www. and .com/.org/etc
            parts = host.replace("www.", "").split(".")
            return parts[0] if parts else ""
        except Exception:
            return ""
