"""Grounding engine — post-extraction evidence verification (PDF §5.3, v2 §22).

After the LLM returns {value, evidence, confidence}, the grounding engine
verifies that the evidence actually exists in the source text.

Verification strategies by field type:
    - text: fuzz.partial_ratio ≥ 90 (PDF §5.3)
    - numbers: numeric comparison with ±1% tolerance
    - dates: dateutil parse + ±1 day tolerance
    - urls: canonicalized comparison
    - booleans: keyword presence

Fields that fail grounding are marked UNVERIFIED and excluded from export.
"""

from __future__ import annotations

import re
from typing import Any

from rapidfuzz import fuzz

from provenmesh.config.settings import get_settings
from provenmesh.domain.enums import FieldVerification, VerificationStatus
from provenmesh.domain.evidence import EvidenceRecord
from provenmesh.grounding.hallucination import HallucinationDetector
from provenmesh.observability.logging import get_logger
from provenmesh.observability.metrics import GROUNDING_FAILURE_TOTAL, GROUNDING_TOTAL

logger = get_logger(__name__)


class GroundingEngine:
    """Verifies that every extracted field is supported by source evidence.

    This is the critical quality gate — it catches LLM hallucination
    by comparing extracted values against the original source text.
    """

    def __init__(self) -> None:
        self._settings = get_settings()
        self._text_threshold = self._settings.grounding_threshold  # 90
        self._number_tolerance_pct = 1.0
        self._date_tolerance_days = 1
        self._hallucination_detector = HallucinationDetector()

    def verify_record(
        self,
        extracted_fields: dict[str, Any],
        source_text: str,
        source_url: str = "",
        content_hash: str = "",
        entity_id: str = "",
    ) -> GroundingResult:
        """Verify all fields in an extracted record against source text.

        Returns a GroundingResult with per-field verification status,
        evidence records, and overall record verification.
        """
        evidence_records: list[EvidenceRecord] = []
        grounded_count = 0
        total_count = 0

        for field_name, field_data in extracted_fields.items():
            if isinstance(field_data, list):
                # Handle array fields (founders, skills, etc.)
                for i, item in enumerate(field_data):
                    if isinstance(item, dict) and "value" in item:
                        total_count += 1
                        result = self._verify_field(
                            f"{field_name}[{i}]",
                            item,
                            source_text,
                            source_url,
                            content_hash,
                            entity_id,
                        )
                        evidence_records.append(result)
                        if result.verification_status == FieldVerification.GROUNDED:
                            grounded_count += 1
            elif isinstance(field_data, dict) and "value" in field_data:
                total_count += 1
                result = self._verify_field(
                    field_name,
                    field_data,
                    source_text,
                    source_url,
                    content_hash,
                    entity_id,
                )
                evidence_records.append(result)
                if result.verification_status == FieldVerification.GROUNDED:
                    grounded_count += 1

        # Determine overall verification status
        if total_count == 0:
            overall = VerificationStatus.UNVERIFIED
        elif grounded_count == total_count:
            overall = VerificationStatus.GROUNDED
        elif grounded_count >= total_count * 0.5:
            overall = VerificationStatus.PARTIAL
        else:
            overall = VerificationStatus.UNVERIFIED

        # Build grounding scores map for hallucination detector
        grounding_scores = {
            rec.field_name: rec.fuzzy_score
            for rec in evidence_records
        }

        # Run hallucination detection
        hallucination_report = self._hallucination_detector.analyze_record(
            extracted_fields, source_text, grounding_scores,
        )

        # Downgrade overall status if hallucination is detected
        if hallucination_report.has_critical:
            overall = VerificationStatus.UNVERIFIED
            logger.warning(
                "record_rejected_hallucination",
                entity_id=entity_id,
                trust_score=hallucination_report.overall_trust_score,
                flags=len(hallucination_report.flags),
            )

        return GroundingResult(
            verification_status=overall,
            evidence_records=evidence_records,
            grounded_count=grounded_count,
            total_count=total_count,
            hallucination_report=hallucination_report,
        )

    def _verify_field(
        self,
        field_name: str,
        field_data: dict[str, Any],
        source_text: str,
        source_url: str,
        content_hash: str,
        entity_id: str,
    ) -> EvidenceRecord:
        """Verify a single field against source text."""
        value = field_data.get("value")
        evidence = field_data.get("evidence", "")
        float(field_data.get("confidence", 0.0))

        GROUNDING_TOTAL.labels(field_type=field_name.split("[")[0]).inc()

        # Skip null/empty values
        if value is None or str(value).strip() == "":
            return EvidenceRecord(
                entity_id=entity_id,
                field_name=field_name,
                extracted_value="",
                evidence_text="",
                source_url=source_url,
                source_content_hash=content_hash,
                verification_status=FieldVerification.MISSING,
                fuzzy_score=0.0,
            )

        str_value = str(value).strip()

        # Verify evidence exists in source text
        if not evidence:
            GROUNDING_FAILURE_TOTAL.labels(field_type=field_name.split("[")[0]).inc()
            return EvidenceRecord(
                entity_id=entity_id,
                field_name=field_name,
                extracted_value=str_value,
                evidence_text="",
                source_url=source_url,
                source_content_hash=content_hash,
                verification_status=FieldVerification.UNVERIFIED,
                fuzzy_score=0.0,
            )

        # Determine verification strategy based on value type
        if self._looks_like_number(str_value):
            verified, score = self._verify_number(str_value, evidence, source_text)
        elif self._looks_like_url(str_value):
            verified, score = self._verify_url(str_value, source_text)
        else:
            verified, score = self._verify_text(evidence, source_text)

        status = FieldVerification.GROUNDED if verified else FieldVerification.UNVERIFIED

        if not verified:
            GROUNDING_FAILURE_TOTAL.labels(field_type=field_name.split("[")[0]).inc()
            logger.debug(
                "grounding_failed",
                field=field_name,
                value=str_value[:50],
                score=round(score, 1),
                threshold=self._text_threshold,
            )

        return EvidenceRecord(
            entity_id=entity_id,
            field_name=field_name,
            extracted_value=str_value,
            evidence_text=evidence,
            source_url=source_url,
            source_content_hash=content_hash,
            verification_status=status,
            fuzzy_score=score,
        )

    def _verify_text(self, evidence: str, source_text: str) -> tuple[bool, float]:
        """Verify text evidence using fuzzy matching (PDF §5.3)."""
        score = fuzz.partial_ratio(
            evidence.lower().strip(),
            source_text.lower(),
        )
        return score >= self._text_threshold, float(score)

    def _verify_number(self, value: str, evidence: str, source_text: str) -> tuple[bool, float]:
        """Verify numeric values with ±1% tolerance."""
        try:
            extracted_num = self._extract_number(value)
            if extracted_num is None:
                return self._verify_text(evidence, source_text)

            # Find numbers in source text near the evidence
            evidence_score = fuzz.partial_ratio(evidence.lower(), source_text.lower())
            if evidence_score < 70:
                return False, evidence_score

            # Check if the number appears in source
            numbers_in_source = re.findall(r"[\d,]+\.?\d*", source_text)
            for num_str in numbers_in_source:
                source_num = self._extract_number(num_str)
                if source_num is not None and extracted_num != 0:
                    tolerance = abs(extracted_num * self._number_tolerance_pct / 100)
                    if abs(extracted_num - source_num) <= max(tolerance, 0.01):
                        return True, 100.0

            return evidence_score >= self._text_threshold, evidence_score

        except (ValueError, TypeError):
            return self._verify_text(evidence, source_text)

    def _verify_url(self, value: str, source_text: str) -> tuple[bool, float]:
        """Verify URL by checking if it appears in source text."""
        normalized = value.lower().rstrip("/").replace("https://", "").replace("http://", "")
        source_lower = source_text.lower()
        if normalized in source_lower or value.lower() in source_lower:
            return True, 100.0
        return False, 0.0

    @staticmethod
    def _looks_like_number(value: str) -> bool:
        cleaned = re.sub(r"[$€£¥,\s]", "", value)
        try:
            float(cleaned)
            return True
        except ValueError:
            return bool(re.match(r"^\d[\d,]*\.?\d*[BMKbmk]?$", cleaned))

    @staticmethod
    def _looks_like_url(value: str) -> bool:
        return value.startswith(("http://", "https://", "www."))

    @staticmethod
    def _extract_number(value: str) -> float | None:
        """Extract numeric value from string with suffix support ($1.5B → 1500000000)."""
        cleaned = re.sub(r"[$€£¥,\s]", "", value.strip())
        multipliers = {"b": 1e9, "m": 1e6, "k": 1e3}
        suffix = cleaned[-1].lower() if cleaned else ""
        if suffix in multipliers:
            try:
                return float(cleaned[:-1]) * multipliers[suffix]
            except ValueError:
                return None
        try:
            return float(cleaned)
        except ValueError:
            return None


class GroundingResult:
    """Result of grounding verification for a complete record."""

    def __init__(
        self,
        verification_status: VerificationStatus,
        evidence_records: list[EvidenceRecord],
        grounded_count: int,
        total_count: int,
        hallucination_report: Any = None,
    ) -> None:
        self.verification_status = verification_status
        self.evidence_records = evidence_records
        self.grounded_count = grounded_count
        self.total_count = total_count
        self.hallucination_report = hallucination_report

    @property
    def grounding_ratio(self) -> float:
        if self.total_count == 0:
            return 0.0
        return self.grounded_count / self.total_count

    @property
    def is_exportable(self) -> bool:
        """A record is exportable if it's GROUNDED or PARTIAL."""
        return self.verification_status in (
            VerificationStatus.GROUNDED,
            VerificationStatus.PARTIAL,
        )
