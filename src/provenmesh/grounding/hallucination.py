"""Hallucination detection — catches LLM fabrication beyond grounding (v2 §22+).

The grounding engine verifies evidence exists in source text, but LLMs can
fabricate BOTH the value AND a plausible-sounding evidence span. This module
adds deeper hallucination checks:

    1. Evidence fabrication — exact substring check (stricter than fuzzy)
    2. Confidence inflation — LLM confidence vs grounding score mismatch
    3. Cross-field consistency — contradictions between related fields
    4. Suspicious patterns — templated/generic evidence, impossible values
    5. Source attribution — evidence must be traceable to source text

Integrate into the grounding pipeline AFTER standard verification.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime

from provenmesh.observability.logging import get_logger
from provenmesh.observability.metrics import (
    HALLUCINATION_CHECK_TOTAL,
    HALLUCINATION_DETECTED_TOTAL,
)

logger = get_logger(__name__)


# ─── Suspicious patterns that suggest fabrication ─────────────────
_GENERIC_EVIDENCE_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"^the company (is|was) founded", re.IGNORECASE),
    re.compile(r"^according to (the|their) website", re.IGNORECASE),
    re.compile(r"^based on (available|public) (data|information)", re.IGNORECASE),
    re.compile(r"^it is (known|reported|stated) that", re.IGNORECASE),
    re.compile(r"^(the |this )?(source|article|page) (states|mentions|says)", re.IGNORECASE),
]

# Values that are suspiciously common LLM fabrications
_SUSPICIOUS_VALUES: set[str] = {
    "2023", "2022", "2021",                  # LLMs default to recent years
    "San Francisco", "Silicon Valley",        # Default HQ assumptions
    "Series A", "Series B",                   # Common funding assumptions
    "AI-powered", "cutting-edge",             # Generic descriptions
}

# Minimum evidence length to be considered real
_MIN_EVIDENCE_LENGTH = 10

# Maximum gap between LLM confidence and grounding score before flagging
_CONFIDENCE_INFLATION_THRESHOLD = 0.35

# Statistical outlier bounds for numeric fields
_OUTLIER_BOUNDS: dict[str, tuple[float, float]] = {
    "fundingTotal": (1_000, 500_000_000_000),      # $1K - $500B
    "employeeCount": (1, 5_000_000),                # 1 - 5M employees
    "salary": (10_000, 10_000_000),                  # $10K - $10M salary
    "citations": (0, 1_000_000),                     # 0 - 1M citations
}

# Expected fields per record type (minimum completeness)
_REQUIRED_FIELDS: dict[str, list[str]] = {
    "STARTUP": ["entityName", "description"],
    "PRODUCT": ["entityName", "description"],
    "PAPER": ["entityName", "description"],
    "JOB": ["entityName", "description"],
    "NEWS": ["entityName", "description"],
}

_URL_PATTERN = re.compile(
    r"^https?://[a-zA-Z0-9]([a-zA-Z0-9\-]*[a-zA-Z0-9])?"
    r"(\.[a-zA-Z0-9]([a-zA-Z0-9\-]*[a-zA-Z0-9])?)*"
    r"(/[^\s]*)?$",
)


@dataclass
class HallucinationFlag:
    """A single detected hallucination signal."""

    field_name: str
    check_type: str  # fabrication, inflation, contradiction, suspicious, attribution
    severity: str    # critical, warning, info
    message: str
    extracted_value: str = ""
    evidence_text: str = ""
    llm_confidence: float = 0.0
    grounding_score: float = 0.0


@dataclass
class HallucinationReport:
    """Aggregated hallucination analysis for a complete record."""

    flags: list[HallucinationFlag] = field(default_factory=list)
    fields_checked: int = 0
    fields_flagged: int = 0
    overall_trust_score: float = 1.0
    recommendation: str = "accept"  # accept, review, reject

    @property
    def has_critical(self) -> bool:
        return any(f.severity == "critical" for f in self.flags)

    @property
    def has_warnings(self) -> bool:
        return any(f.severity == "warning" for f in self.flags)

    @property
    def is_trustworthy(self) -> bool:
        return not self.has_critical and self.overall_trust_score >= 0.6


class HallucinationDetector:
    """Multi-layer hallucination detection for LLM-extracted records.

    Runs AFTER the grounding engine to catch subtle fabrications that
    pass fuzzy matching but are still hallucinated.
    """

    def __init__(
        self,
        confidence_inflation_threshold: float = _CONFIDENCE_INFLATION_THRESHOLD,
        min_evidence_length: int = _MIN_EVIDENCE_LENGTH,
    ) -> None:
        self._inflation_threshold = confidence_inflation_threshold
        self._min_evidence_length = min_evidence_length

    def analyze_record(
        self,
        extracted_fields: dict,
        source_text: str,
        grounding_scores: dict[str, float] | None = None,
        record_type: str = "",
    ) -> HallucinationReport:
        """Run all hallucination checks on an extracted record.

        Args:
            extracted_fields: LLM-extracted {field: {value, evidence, confidence}}
            source_text: Original source HTML/text
            grounding_scores: Optional per-field grounding scores from engine

        Returns:
            HallucinationReport with all detected flags
        """
        grounding_scores = grounding_scores or {}
        report = HallucinationReport()

        for field_name, field_data in extracted_fields.items():
            if isinstance(field_data, list):
                for i, item in enumerate(field_data):
                    if isinstance(item, dict) and "value" in item:
                        indexed_name = f"{field_name}[{i}]"
                        self._check_field(
                            indexed_name, item, source_text,
                            grounding_scores.get(indexed_name, 0.0),
                            report,
                        )
            elif isinstance(field_data, dict) and "value" in field_data:
                self._check_field(
                    field_name, field_data, source_text,
                    grounding_scores.get(field_name, 0.0),
                    report,
                )

        # Record-level checks (multi-field analysis)
        self._check_cross_field_consistency(extracted_fields, report)
        self._check_duplicate_evidence(extracted_fields, report)
        self._check_confidence_uniformity(extracted_fields, report)
        self._check_completeness(extracted_fields, record_type, report)

        # Calculate overall trust score
        report.overall_trust_score = self._compute_trust_score(report)
        report.recommendation = self._recommend(report)

        HALLUCINATION_CHECK_TOTAL.inc(report.fields_checked)

        if report.flags:
            HALLUCINATION_DETECTED_TOTAL.labels(
                severity="critical" if report.has_critical else "warning",
            ).inc(len(report.flags))
            logger.warning(
                "hallucination_flags_detected",
                flags=len(report.flags),
                critical=report.has_critical,
                trust_score=round(report.overall_trust_score, 2),
                recommendation=report.recommendation,
            )

        return report

    def _check_field(
        self,
        field_name: str,
        field_data: dict,
        source_text: str,
        grounding_score: float,
        report: HallucinationReport,
    ) -> None:
        """Run all hallucination checks on a single field."""
        value = field_data.get("value")
        evidence = field_data.get("evidence", "")
        confidence = float(field_data.get("confidence", 0.0))

        if value is None or str(value).strip() == "":
            return  # Skip null/empty fields

        report.fields_checked += 1
        str_value = str(value).strip()
        flagged = False

        # Check 1: Evidence fabrication (exact substring check)
        fab_flag = self._check_evidence_fabrication(
            field_name, str_value, evidence, source_text,
        )
        if fab_flag:
            report.flags.append(fab_flag)
            flagged = True

        # Check 2: Confidence inflation
        inf_flag = self._check_confidence_inflation(
            field_name, str_value, evidence, confidence, grounding_score,
        )
        if inf_flag:
            report.flags.append(inf_flag)
            flagged = True

        # Check 3: Suspicious patterns
        sus_flag = self._check_suspicious_patterns(
            field_name, str_value, evidence, confidence,
        )
        if sus_flag:
            report.flags.append(sus_flag)
            flagged = True

        # Check 4: Source attribution
        attr_flag = self._check_source_attribution(
            field_name, str_value, evidence, source_text,
        )
        if attr_flag:
            report.flags.append(attr_flag)
            flagged = True

        # Check 5: URL format validation
        url_flag = self._check_url_format(field_name, str_value)
        if url_flag:
            report.flags.append(url_flag)
            flagged = True

        # Check 6: Statistical outlier detection
        outlier_flag = self._check_statistical_outlier(
            field_name, str_value,
        )
        if outlier_flag:
            report.flags.append(outlier_flag)
            flagged = True

        if flagged:
            report.fields_flagged += 1

    def _check_evidence_fabrication(
        self,
        field_name: str,
        value: str,
        evidence: str,
        source_text: str,
    ) -> HallucinationFlag | None:
        """Check if evidence is fabricated — EXACT substring match.

        The grounding engine uses fuzzy matching (90% threshold), but a
        fabricated evidence span might still score above 90% if it shares
        enough words with the source. This check requires the evidence to
        exist as a near-exact substring.
        """
        if not evidence or len(evidence) < self._min_evidence_length:
            return HallucinationFlag(
                field_name=field_name,
                check_type="fabrication",
                severity="warning",
                message="Evidence too short or missing — possible fabrication",
                extracted_value=value,
                evidence_text=evidence,
            )

        # Normalize whitespace for comparison
        norm_evidence = " ".join(evidence.lower().split())
        norm_source = " ".join(source_text.lower().split())

        # Check if evidence is a substring of source (exact)
        if norm_evidence in norm_source:
            return None  # Evidence genuinely exists in source

        # Try sliding window: check if any contiguous substring of source
        # matches at least 80% of the evidence words
        evidence_words = norm_evidence.split()
        if len(evidence_words) < 3:
            return None  # Too short for reliable fabrication detection

        # Check word-level overlap (at least 70% of evidence words must
        # appear in source within a reasonable window)
        source_words_set = set(norm_source.split())
        matching_words = sum(1 for w in evidence_words if w in source_words_set)
        overlap_ratio = matching_words / len(evidence_words)

        if overlap_ratio < 0.7:
            return HallucinationFlag(
                field_name=field_name,
                check_type="fabrication",
                severity="critical",
                message=(
                    f"Evidence likely fabricated — only {overlap_ratio:.0%} word overlap "
                    f"with source text"
                ),
                extracted_value=value,
                evidence_text=evidence[:100],
            )

        return None

    def _check_confidence_inflation(
        self,
        field_name: str,
        value: str,
        evidence: str,
        llm_confidence: float,
        grounding_score: float,
    ) -> HallucinationFlag | None:
        """Detect when LLM reports high confidence but grounding score is low.

        A gap > 0.35 between LLM confidence and grounding score is suspicious
        because it means the LLM is "sure" about something the evidence
        doesn't support.
        """
        if grounding_score == 0.0:
            return None  # No grounding score available

        # Normalize grounding score to 0-1 (it may come as 0-100)
        norm_grounding = grounding_score / 100.0 if grounding_score > 1.0 else grounding_score

        gap = llm_confidence - norm_grounding

        if gap > self._inflation_threshold:
            return HallucinationFlag(
                field_name=field_name,
                check_type="inflation",
                severity="warning",
                message=(
                    f"Confidence inflation: LLM={llm_confidence:.2f} vs "
                    f"grounding={norm_grounding:.2f} (gap={gap:.2f})"
                ),
                extracted_value=value,
                evidence_text=evidence[:80],
                llm_confidence=llm_confidence,
                grounding_score=norm_grounding,
            )

        return None

    def _check_suspicious_patterns(
        self,
        field_name: str,
        value: str,
        evidence: str,
        confidence: float,
    ) -> HallucinationFlag | None:
        """Detect common hallucination patterns.

        Checks for:
        - Generic/templated evidence (e.g., "According to the source...")
        - Suspiciously high confidence on fields LLMs commonly fabricate
        - Impossible values (negative funding, dates in the future)
        """
        # Check for generic evidence patterns
        if evidence:
            for pattern in _GENERIC_EVIDENCE_PATTERNS:
                if pattern.search(evidence):
                    return HallucinationFlag(
                        field_name=field_name,
                        check_type="suspicious",
                        severity="warning",
                        message=f"Generic/templated evidence pattern detected: '{evidence[:60]}'",
                        extracted_value=value,
                        evidence_text=evidence[:100],
                    )

        # Check for high confidence on commonly-fabricated values
        if value in _SUSPICIOUS_VALUES and confidence > 0.9:
            return HallucinationFlag(
                field_name=field_name,
                check_type="suspicious",
                severity="info",
                message=(
                    f"High confidence ({confidence:.2f}) on commonly-assumed "
                    f"value '{value}' — verify manually"
                ),
                extracted_value=value,
                evidence_text=evidence[:80],
                llm_confidence=confidence,
            )

        # Check for impossible future dates
        if field_name in ("foundedDate", "publishedDate", "postedDate"):
            try:
                year = int(re.search(r"\d{4}", value).group())  # type: ignore[union-attr]
                current_year = datetime.now().year  # noqa: DTZ005
                if year > current_year + 1:
                    return HallucinationFlag(
                        field_name=field_name,
                        check_type="suspicious",
                        severity="critical",
                        message=f"Impossible future date: {value}",
                        extracted_value=value,
                        evidence_text=evidence[:80],
                    )
            except (AttributeError, ValueError):
                pass  # Not a parseable date, skip

        return None

    def _check_source_attribution(
        self,
        field_name: str,
        value: str,
        evidence: str,
        source_text: str,
    ) -> HallucinationFlag | None:
        """Check if the extracted VALUE itself can be found in source text.

        Even if evidence passes grounding, the actual value must be present
        in the source. An LLM might provide real evidence but extract a
        wrong value from it.
        """
        if not value or len(value) < 3:
            return None  # Skip very short values (e.g., "AI")

        value_lower = value.lower().strip()
        source_lower = source_text.lower()

        # Direct substring check
        if value_lower in source_lower:
            return None  # Value genuinely exists in source

        # For numbers, check if the numeric value exists
        try:
            num = float(re.sub(r"[$€£¥,\s]", "", value))
            if str(int(num)) in source_text or str(num) in source_text:
                return None
        except (ValueError, OverflowError):
            pass

        # For multi-word values, check if at least 60% of words appear
        words = value_lower.split()
        if len(words) >= 2:
            source_words = set(source_lower.split())
            matching = sum(1 for w in words if w in source_words)
            if matching / len(words) >= 0.6:
                return None  # Enough word overlap

        return HallucinationFlag(
            field_name=field_name,
            check_type="attribution",
            severity="warning",
            message=(
                f"Extracted value '{value[:50]}' not found in source text — "
                f"possible hallucination"
            ),
            extracted_value=value,
            evidence_text=evidence[:80],
        )

    def _check_cross_field_consistency(
        self,
        fields: dict,
        report: HallucinationReport,
    ) -> None:
        """Check for contradictions between related fields.

        Examples:
        - Founded date says 2015 but description says "founded in 2020"
        - HQ says "London" but website is .com/san-francisco
        - Funding says "$1M" but description says "raised $10B"
        """
        founded_date = self._get_field_value(fields, "foundedDate")
        description = self._get_field_value(fields, "description")

        if founded_date and description:
            # Check if founded year appears in description with different year
            try:
                year = re.search(r"\d{4}", founded_date)
                if year:
                    desc_years = re.findall(
                        r"founded\s+(?:in\s+)?(\d{4})",
                        description,
                        re.IGNORECASE,
                    )
                    for desc_year in desc_years:
                        if desc_year != year.group():
                            report.flags.append(HallucinationFlag(
                                field_name="foundedDate↔description",
                                check_type="contradiction",
                                severity="critical",
                                message=(
                                    f"Date contradiction: foundedDate='{founded_date}' but "
                                    f"description mentions 'founded {desc_year}'"
                                ),
                                extracted_value=founded_date,
                            ))
            except (AttributeError, ValueError):
                pass

        # Check funding contradictions
        funding = self._get_field_value(fields, "fundingTotal")
        if funding and description:
            funding_nums = re.findall(r"\$[\d.]+\s*[BMK]", funding, re.IGNORECASE)
            desc_nums = re.findall(r"\$[\d.]+\s*[BMK]", description, re.IGNORECASE)
            if (
                funding_nums
                and desc_nums
                and funding_nums[0].lower() != desc_nums[0].lower()
            ):
                report.flags.append(HallucinationFlag(
                    field_name="fundingTotal↔description",
                    check_type="contradiction",
                    severity="warning",
                    message=(
                        f"Funding mismatch: fundingTotal='{funding}' but "
                        f"description mentions '{desc_nums[0]}'"
                    ),
                    extracted_value=funding,
                ))

    @staticmethod
    def _get_field_value(fields: dict, name: str) -> str | None:
        """Extract the string value from a field dict."""
        data = fields.get(name)
        if isinstance(data, dict) and "value" in data:
            val = data["value"]
            return str(val) if val is not None else None
        return None

    # ─── Advanced Detection Layer 6: Duplicate Evidence ───────────

    def _check_duplicate_evidence(
        self,
        fields: dict,
        report: HallucinationReport,
    ) -> None:
        """Detect when multiple fields share identical evidence text.

        LLMs sometimes copy-paste the same evidence span for different
        fields — a sign of lazy generation, not real extraction.
        """
        evidence_map: dict[str, list[str]] = {}
        for field_name, field_data in fields.items():
            if isinstance(field_data, list):
                for i, item in enumerate(field_data):
                    if isinstance(item, dict) and item.get("evidence"):
                        ev = item["evidence"].strip().lower()
                        if len(ev) >= self._min_evidence_length:
                            evidence_map.setdefault(ev, []).append(
                                f"{field_name}[{i}]",
                            )
            elif isinstance(field_data, dict) and field_data.get("evidence"):
                ev = field_data["evidence"].strip().lower()
                if len(ev) >= self._min_evidence_length:
                    evidence_map.setdefault(ev, []).append(field_name)

        for evidence, field_names in evidence_map.items():
            if len(field_names) >= 3:
                report.flags.append(HallucinationFlag(
                    field_name="↔".join(field_names[:3]),
                    check_type="duplicate_evidence",
                    severity="warning",
                    message=(
                        f"{len(field_names)} fields share identical evidence: "
                        f"'{evidence[:60]}'"
                    ),
                ))

    # ─── Advanced Detection Layer 7: Confidence Uniformity ────────

    @staticmethod
    def _check_confidence_uniformity(
        fields: dict,
        report: HallucinationReport,
    ) -> None:
        """Detect when all confidences are suspiciously identical.

        Real extraction produces varied confidence scores. If the LLM
        returns exactly 0.95 for every field, it didn't actually calibrate.
        """
        confidences: list[float] = []
        for field_data in fields.values():
            if isinstance(field_data, list):
                for item in field_data:
                    if isinstance(item, dict) and "confidence" in item:
                        confidences.append(float(item["confidence"]))
            elif isinstance(field_data, dict) and "confidence" in field_data:
                confidences.append(float(field_data["confidence"]))

        if len(confidences) >= 4:
            unique = set(round(c, 3) for c in confidences)
            if len(unique) == 1:
                report.flags.append(HallucinationFlag(
                    field_name="*",
                    check_type="uniformity",
                    severity="warning",
                    message=(
                        f"All {len(confidences)} fields have identical "
                        f"confidence={confidences[0]:.2f} — not calibrated"
                    ),
                    llm_confidence=confidences[0],
                ))

    # ─── Advanced Detection Layer 8: Completeness Scoring ─────────

    @staticmethod
    def _check_completeness(
        fields: dict,
        record_type: str,
        report: HallucinationReport,
    ) -> None:
        """Flag records missing critical fields for their type."""
        if not record_type:
            return

        required = _REQUIRED_FIELDS.get(record_type.upper(), [])
        if not required:
            return

        missing = []
        for req_field in required:
            data = fields.get(req_field)
            if data is None:
                missing.append(req_field)
            elif isinstance(data, dict):
                val = data.get("value")
                if val is None or str(val).strip() == "":
                    missing.append(req_field)

        if missing:
            report.flags.append(HallucinationFlag(
                field_name=",".join(missing),
                check_type="completeness",
                severity="warning" if len(missing) == 1 else "critical",
                message=(
                    f"Missing {len(missing)} required field(s) for "
                    f"{record_type}: {', '.join(missing)}"
                ),
            ))

    # ─── Advanced Detection Layer 9: URL Format Validation ────────

    @staticmethod
    def _check_url_format(
        field_name: str,
        value: str,
    ) -> HallucinationFlag | None:
        """Validate that URL-typed fields have valid URL structure.

        LLMs sometimes fabricate plausible-looking but malformed URLs.
        """
        url_fields = {"website", "url", "sourceUrl", "githubUrl"}

        # Extract base field name (strip array index)
        base_name = field_name.split("[")[0]
        if base_name not in url_fields:
            return None

        if not value.startswith(("http://", "https://")):
            return HallucinationFlag(
                field_name=field_name,
                check_type="url_format",
                severity="warning",
                message=f"URL missing protocol: '{value[:60]}'",
                extracted_value=value,
            )

        if not _URL_PATTERN.match(value):
            return HallucinationFlag(
                field_name=field_name,
                check_type="url_format",
                severity="warning",
                message=f"Malformed URL structure: '{value[:60]}'",
                extracted_value=value,
            )

        return None

    # ─── Advanced Detection Layer 10: Statistical Outlier ─────────

    @staticmethod
    def _check_statistical_outlier(
        field_name: str,
        value: str,
    ) -> HallucinationFlag | None:
        """Flag values outside reasonable statistical bounds.

        Catches absurd LLM outputs like $999T funding or -500 employees.
        """
        base_name = field_name.split("[")[0]
        bounds = _OUTLIER_BOUNDS.get(base_name)
        if not bounds:
            return None

        # Try to extract numeric value
        cleaned = re.sub(r"[$€£¥,\s]", "", value.strip())
        multipliers = {"t": 1e12, "b": 1e9, "m": 1e6, "k": 1e3}
        suffix = cleaned[-1].lower() if cleaned else ""

        try:
            if suffix in multipliers:
                num = float(cleaned[:-1]) * multipliers[suffix]
            else:
                num = float(cleaned)
        except (ValueError, IndexError):
            return None  # Not a number, skip

        low, high = bounds
        if num < low or num > high:
            return HallucinationFlag(
                field_name=field_name,
                check_type="outlier",
                severity="critical",
                message=(
                    f"Value {value} ({num:,.0f}) outside reasonable range "
                    f"[{low:,.0f} - {high:,.0f}]"
                ),
                extracted_value=value,
            )

        return None

    @staticmethod
    def _compute_trust_score(report: HallucinationReport) -> float:
        """Compute overall trust score (0.0-1.0) based on flags."""
        if report.fields_checked == 0:
            return 0.0

        penalty = 0.0
        for flag in report.flags:
            if flag.severity == "critical":
                penalty += 0.25
            elif flag.severity == "warning":
                penalty += 0.10
            else:  # info
                penalty += 0.03

        return max(0.0, min(1.0, 1.0 - penalty))

    @staticmethod
    def _recommend(report: HallucinationReport) -> str:
        """Determine action recommendation based on trust score."""
        if report.has_critical or report.overall_trust_score < 0.4:
            return "reject"
        elif report.has_warnings or report.overall_trust_score < 0.7:
            return "review"
        return "accept"
