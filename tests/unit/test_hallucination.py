"""Tests for hallucination detection module.

Covers all 10 detection layers:
    1. Evidence fabrication (exact substring check)
    2. Confidence inflation (LLM vs grounding gap)
    3. Cross-field consistency (contradictions)
    4. Suspicious patterns (templated evidence, impossible values)
    5. Source attribution (value not in source)
    6. Duplicate evidence (lazy copy-paste)
    7. Confidence uniformity (uncalibrated scores)
    8. Completeness scoring (missing required fields)
    9. URL format validation (malformed URLs)
    10. Statistical outlier detection (absurd values)
"""

from __future__ import annotations

from provenmesh.grounding.hallucination import (
    HallucinationDetector,
    HallucinationFlag,
    HallucinationReport,
)

# ─── Sample source text ──────────────────────────────────────────
SOURCE_TEXT = """
OpenAI is an AI safety company founded in 2015 by Sam Altman and Elon Musk.
The company is headquartered in San Francisco, California.
OpenAI has raised $11.3 billion in total funding.
Their flagship product is ChatGPT, launched in November 2022.
Website: https://openai.com
"""

CLEAN_FIELDS = {
    "entityName": {
        "value": "OpenAI",
        "evidence": "OpenAI is an AI safety company",
        "confidence": 0.99,
    },
    "description": {
        "value": "AI safety company",
        "evidence": "OpenAI is an AI safety company",
        "confidence": 0.95,
    },
    "foundedDate": {
        "value": "2015",
        "evidence": "founded in 2015",
        "confidence": 0.95,
    },
    "headquarters": {
        "value": "San Francisco",
        "evidence": "headquartered in San Francisco",
        "confidence": 0.93,
    },
    "fundingTotal": {
        "value": "$11.3 billion",
        "evidence": "raised $11.3 billion in total funding",
        "confidence": 0.97,
    },
    "website": {
        "value": "https://openai.com",
        "evidence": "Website: https://openai.com",
        "confidence": 0.99,
    },
}


class TestHallucinationReport:
    def test_empty_report(self) -> None:
        report = HallucinationReport()
        assert not report.has_critical
        assert not report.has_warnings
        assert report.is_trustworthy
        assert report.fields_checked == 0

    def test_critical_flag(self) -> None:
        report = HallucinationReport(
            flags=[
                HallucinationFlag(
                    field_name="test",
                    check_type="fabrication",
                    severity="critical",
                    message="fabricated",
                ),
            ]
        )
        assert report.has_critical
        assert not report.is_trustworthy

    def test_warning_flag(self) -> None:
        report = HallucinationReport(
            flags=[
                HallucinationFlag(
                    field_name="test",
                    check_type="inflation",
                    severity="warning",
                    message="inflated",
                ),
            ]
        )
        assert not report.has_critical
        assert report.has_warnings

    def test_trustworthy_with_info(self) -> None:
        report = HallucinationReport(
            flags=[
                HallucinationFlag(
                    field_name="test",
                    check_type="suspicious",
                    severity="info",
                    message="suspicious",
                ),
            ],
            overall_trust_score=0.9,
        )
        assert report.is_trustworthy


class TestEvidenceFabrication:
    def test_genuine_evidence_passes(self) -> None:
        detector = HallucinationDetector()
        report = detector.analyze_record(CLEAN_FIELDS, SOURCE_TEXT)
        fabrication_flags = [f for f in report.flags if f.check_type == "fabrication"]
        assert len(fabrication_flags) == 0

    def test_fabricated_evidence_detected(self) -> None:
        detector = HallucinationDetector()
        fields = {
            "entityName": {
                "value": "FakeCompany",
                "evidence": (
                    "FakeCompany is a revolutionary quantum blockchain "
                    "startup disrupting markets"
                ),
                "confidence": 0.95,
            },
        }
        report = detector.analyze_record(fields, SOURCE_TEXT)
        fabrication_flags = [f for f in report.flags if f.check_type == "fabrication"]
        assert len(fabrication_flags) >= 1
        assert fabrication_flags[0].severity == "critical"

    def test_short_evidence_warning(self) -> None:
        detector = HallucinationDetector()
        fields = {
            "entityName": {
                "value": "OpenAI",
                "evidence": "short",
                "confidence": 0.95,
            },
        }
        report = detector.analyze_record(fields, SOURCE_TEXT)
        fabrication_flags = [f for f in report.flags if f.check_type == "fabrication"]
        assert len(fabrication_flags) >= 1
        assert fabrication_flags[0].severity == "warning"

    def test_empty_evidence_warning(self) -> None:
        detector = HallucinationDetector()
        fields = {
            "entityName": {
                "value": "OpenAI",
                "evidence": "",
                "confidence": 0.95,
            },
        }
        report = detector.analyze_record(fields, SOURCE_TEXT)
        fabrication_flags = [f for f in report.flags if f.check_type == "fabrication"]
        assert len(fabrication_flags) >= 1

    def test_two_word_evidence_skipped(self) -> None:
        """Evidence with < 3 words is too short for fabrication check."""
        detector = HallucinationDetector()
        fields = {
            "entityName": {
                "value": "OpenAI",
                "evidence": "OpenAI company",
                "confidence": 0.95,
            },
        }
        report = detector.analyze_record(fields, SOURCE_TEXT)
        fabrication_flags = [
            f for f in report.flags if f.check_type == "fabrication"
        ]
        # 2-word evidence skips fabrication detection
        assert len(fabrication_flags) == 0


class TestConfidenceInflation:
    def test_no_inflation_when_aligned(self) -> None:
        detector = HallucinationDetector()
        grounding_scores = {"entityName": 95.0}
        report = detector.analyze_record(
            {"entityName": CLEAN_FIELDS["entityName"]},
            SOURCE_TEXT,
            grounding_scores,
        )
        inflation_flags = [f for f in report.flags if f.check_type == "inflation"]
        assert len(inflation_flags) == 0

    def test_inflation_detected(self) -> None:
        detector = HallucinationDetector()
        grounding_scores = {"entityName": 40.0}  # Low grounding
        fields = {
            "entityName": {
                "value": "OpenAI",
                "evidence": "OpenAI is an AI safety company",
                "confidence": 0.99,  # High LLM confidence
            },
        }
        report = detector.analyze_record(fields, SOURCE_TEXT, grounding_scores)
        inflation_flags = [f for f in report.flags if f.check_type == "inflation"]
        assert len(inflation_flags) >= 1
        assert inflation_flags[0].llm_confidence == 0.99

    def test_no_inflation_without_grounding_score(self) -> None:
        detector = HallucinationDetector()
        report = detector.analyze_record(
            {"entityName": CLEAN_FIELDS["entityName"]},
            SOURCE_TEXT,
            {},  # No grounding scores
        )
        inflation_flags = [f for f in report.flags if f.check_type == "inflation"]
        assert len(inflation_flags) == 0

    def test_inflation_with_fractional_grounding(self) -> None:
        """Test grounding scores already in 0-1 range."""
        detector = HallucinationDetector()
        grounding_scores = {"entityName": 0.40}  # Already 0-1 scale
        fields = {
            "entityName": {
                "value": "OpenAI",
                "evidence": "OpenAI is an AI safety company",
                "confidence": 0.99,
            },
        }
        report = detector.analyze_record(fields, SOURCE_TEXT, grounding_scores)
        inflation_flags = [f for f in report.flags if f.check_type == "inflation"]
        assert len(inflation_flags) >= 1


class TestSuspiciousPatterns:
    def test_generic_evidence_detected(self) -> None:
        detector = HallucinationDetector()
        fields = {
            "entityName": {
                "value": "OpenAI",
                "evidence": "According to their website, OpenAI is an AI company",
                "confidence": 0.90,
            },
        }
        report = detector.analyze_record(fields, SOURCE_TEXT)
        suspicious_flags = [f for f in report.flags if f.check_type == "suspicious"]
        assert len(suspicious_flags) >= 1

    def test_the_source_states_pattern(self) -> None:
        detector = HallucinationDetector()
        fields = {
            "entityName": {
                "value": "OpenAI",
                "evidence": "The source states that OpenAI is a company",
                "confidence": 0.90,
            },
        }
        report = detector.analyze_record(fields, SOURCE_TEXT)
        suspicious_flags = [f for f in report.flags if f.check_type == "suspicious"]
        assert len(suspicious_flags) >= 1

    def test_suspicious_value_high_confidence(self) -> None:
        detector = HallucinationDetector()
        fields = {
            "foundedDate": {
                "value": "2023",
                "evidence": "founded in 2015",
                "confidence": 0.95,
            },
        }
        report = detector.analyze_record(fields, SOURCE_TEXT)
        suspicious_flags = [f for f in report.flags if f.check_type == "suspicious"]
        assert any(f.severity == "info" for f in suspicious_flags)

    def test_impossible_future_date(self) -> None:
        detector = HallucinationDetector()
        fields = {
            "foundedDate": {
                "value": "2099-01-01",
                "evidence": "founded in 2015",
                "confidence": 0.90,
            },
        }
        report = detector.analyze_record(fields, SOURCE_TEXT)
        suspicious_flags = [f for f in report.flags if f.check_type == "suspicious"]
        assert any(f.severity == "critical" for f in suspicious_flags)
        assert any("Impossible future date" in f.message for f in suspicious_flags)

    def test_non_date_field_skips_date_check(self) -> None:
        detector = HallucinationDetector()
        fields = {
            "entityName": {
                "value": "2099",
                "evidence": "OpenAI is an AI safety company",
                "confidence": 0.90,
            },
        }
        report = detector.analyze_record(fields, SOURCE_TEXT)
        # Should not flag impossible future date for non-date fields
        suspicious_flags = [f for f in report.flags if "Impossible future date" in f.message]
        assert len(suspicious_flags) == 0

    def test_unparseable_date_skipped(self) -> None:
        detector = HallucinationDetector()
        fields = {
            "foundedDate": {
                "value": "not a date",
                "evidence": "founded in 2015",
                "confidence": 0.90,
            },
        }
        report = detector.analyze_record(fields, SOURCE_TEXT)
        # Should not crash on unparseable dates
        assert isinstance(report, HallucinationReport)

    def test_normal_evidence_not_flagged(self) -> None:
        detector = HallucinationDetector()
        report = detector.analyze_record(CLEAN_FIELDS, SOURCE_TEXT)
        suspicious_flags = [f for f in report.flags if f.check_type == "suspicious"]
        # Clean data should not trigger generic evidence patterns
        pattern_flags = [f for f in suspicious_flags if "Generic" in f.message]
        assert len(pattern_flags) == 0


class TestSourceAttribution:
    def test_value_in_source_passes(self) -> None:
        detector = HallucinationDetector()
        report = detector.analyze_record(CLEAN_FIELDS, SOURCE_TEXT)
        attr_flags = [f for f in report.flags if f.check_type == "attribution"]
        assert len(attr_flags) == 0

    def test_fabricated_value_detected(self) -> None:
        detector = HallucinationDetector()
        fields = {
            "headquarters": {
                "value": "Tokyo, Japan",
                "evidence": "headquartered in San Francisco",
                "confidence": 0.93,
            },
        }
        report = detector.analyze_record(fields, SOURCE_TEXT)
        attr_flags = [f for f in report.flags if f.check_type == "attribution"]
        assert len(attr_flags) >= 1

    def test_short_value_skipped(self) -> None:
        """Values shorter than 3 chars are skipped."""
        detector = HallucinationDetector()
        fields = {
            "industry": {
                "value": "AI",
                "evidence": "OpenAI is an AI safety company",
                "confidence": 0.95,
            },
        }
        report = detector.analyze_record(fields, SOURCE_TEXT)
        attr_flags = [f for f in report.flags if f.check_type == "attribution"]
        assert len(attr_flags) == 0

    def test_numeric_value_in_source(self) -> None:
        detector = HallucinationDetector()
        fields = {
            "fundingTotal": {
                "value": "$11.3",
                "evidence": "raised $11.3 billion",
                "confidence": 0.97,
            },
        }
        report = detector.analyze_record(fields, SOURCE_TEXT)
        attr_flags = [f for f in report.flags if f.check_type == "attribution"]
        assert len(attr_flags) == 0

    def test_multiword_partial_overlap(self) -> None:
        """Multi-word value with ≥60% word overlap passes."""
        detector = HallucinationDetector()
        fields = {
            "description": {
                "value": "AI safety company in San Francisco",
                "evidence": "OpenAI is an AI safety company",
                "confidence": 0.90,
            },
        }
        report = detector.analyze_record(fields, SOURCE_TEXT)
        attr_flags = [f for f in report.flags if f.check_type == "attribution"]
        assert len(attr_flags) == 0


class TestCrossFieldConsistency:
    def test_consistent_fields_pass(self) -> None:
        detector = HallucinationDetector()
        report = detector.analyze_record(CLEAN_FIELDS, SOURCE_TEXT)
        contradiction_flags = [f for f in report.flags if f.check_type == "contradiction"]
        assert len(contradiction_flags) == 0

    def test_date_contradiction_detected(self) -> None:
        detector = HallucinationDetector()
        fields = {
            "foundedDate": {
                "value": "2015",
                "evidence": "founded in 2015",
                "confidence": 0.95,
            },
            "description": {
                "value": "AI company founded in 2020",
                "evidence": "AI company founded in 2020",
                "confidence": 0.90,
            },
        }
        report = detector.analyze_record(fields, SOURCE_TEXT)
        contradiction_flags = [f for f in report.flags if f.check_type == "contradiction"]
        assert len(contradiction_flags) >= 1
        assert contradiction_flags[0].severity == "critical"

    def test_funding_mismatch_detected(self) -> None:
        detector = HallucinationDetector()
        fields = {
            "fundingTotal": {
                "value": "$1M",
                "evidence": "raised $11.3 billion",
                "confidence": 0.90,
            },
            "description": {
                "value": "Company raised $10B",
                "evidence": "raised $11.3 billion",
                "confidence": 0.90,
            },
        }
        report = detector.analyze_record(fields, SOURCE_TEXT)
        contradiction_flags = [f for f in report.flags if f.check_type == "contradiction"]
        assert len(contradiction_flags) >= 1


class TestTrustScoreAndRecommendation:
    def test_clean_record_accepted(self) -> None:
        detector = HallucinationDetector()
        report = detector.analyze_record(CLEAN_FIELDS, SOURCE_TEXT)
        assert report.overall_trust_score >= 0.6
        assert report.recommendation == "accept"

    def test_critical_flags_reject(self) -> None:
        detector = HallucinationDetector()
        fields = {
            "entityName": {
                "value": "FakeCompany",
                "evidence": "FakeCompany is a quantum blockchain disruption accelerator initiative",
                "confidence": 0.99,
            },
        }
        report = detector.analyze_record(fields, SOURCE_TEXT)
        assert report.recommendation == "reject"

    def test_warning_flags_review(self) -> None:
        detector = HallucinationDetector()
        fields = {
            "entityName": {
                "value": "OpenAI",
                "evidence": "Based on available data, OpenAI is a company",
                "confidence": 0.90,
            },
        }
        report = detector.analyze_record(fields, SOURCE_TEXT)
        assert report.recommendation in ("review", "reject")

    def test_zero_fields_zero_trust(self) -> None:
        detector = HallucinationDetector()
        report = detector.analyze_record({}, SOURCE_TEXT)
        assert report.overall_trust_score == 0.0
        assert report.recommendation == "reject"


class TestArrayFields:
    def test_array_fields_checked(self) -> None:
        detector = HallucinationDetector()
        fields = {
            "founders": [
                {"value": "Sam Altman", "evidence": "by Sam Altman", "confidence": 0.95},
                {"value": "Elon Musk", "evidence": "and Elon Musk", "confidence": 0.93},
            ],
        }
        report = detector.analyze_record(fields, SOURCE_TEXT)
        assert report.fields_checked == 2

    def test_fabricated_array_item_detected(self) -> None:
        detector = HallucinationDetector()
        fields = {
            "founders": [
                {"value": "Sam Altman", "evidence": "by Sam Altman", "confidence": 0.95},
                {
                    "value": "Mark Zuckerberg",
                    "evidence": (
                        "co-founded by Mark Zuckerberg "
                        "with a vision to transform social media"
                    ),
                    "confidence": 0.90,
                },
            ],
        }
        report = detector.analyze_record(fields, SOURCE_TEXT)
        assert report.fields_flagged >= 1


class TestNullAndEdgeCases:
    def test_null_value_skipped(self) -> None:
        detector = HallucinationDetector()
        fields = {
            "entityName": {"value": None, "evidence": "", "confidence": 0.0},
        }
        report = detector.analyze_record(fields, SOURCE_TEXT)
        assert report.fields_checked == 0

    def test_empty_value_skipped(self) -> None:
        detector = HallucinationDetector()
        fields = {
            "entityName": {"value": "  ", "evidence": "", "confidence": 0.0},
        }
        report = detector.analyze_record(fields, SOURCE_TEXT)
        assert report.fields_checked == 0

    def test_non_dict_field_skipped(self) -> None:
        detector = HallucinationDetector()
        fields = {"plainField": "just a string"}
        report = detector.analyze_record(fields, SOURCE_TEXT)
        assert report.fields_checked == 0

    def test_custom_thresholds(self) -> None:
        detector = HallucinationDetector(
            confidence_inflation_threshold=0.1,
            min_evidence_length=20,
        )
        fields = {
            "entityName": {
                "value": "OpenAI",
                "evidence": "short",
                "confidence": 0.5,
            },
        }
        grounding_scores = {"entityName": 95.0}
        report = detector.analyze_record(fields, SOURCE_TEXT, grounding_scores)
        # Short evidence (< 20 chars) should be flagged as fabrication
        fabrication_flags = [f for f in report.flags if f.check_type == "fabrication"]
        assert len(fabrication_flags) >= 1

    def test_get_field_value_non_dict(self) -> None:
        result = HallucinationDetector._get_field_value({"x": "string"}, "x")
        assert result is None

    def test_get_field_value_none_value(self) -> None:
        result = HallucinationDetector._get_field_value(
            {"x": {"value": None}},
            "x",
        )
        assert result is None


class TestDuplicateEvidence:
    def test_no_duplicates_passes(self) -> None:
        detector = HallucinationDetector()
        report = detector.analyze_record(CLEAN_FIELDS, SOURCE_TEXT)
        dup_flags = [
            f for f in report.flags if f.check_type == "duplicate_evidence"
        ]
        assert len(dup_flags) == 0

    def test_three_fields_same_evidence_flagged(self) -> None:
        detector = HallucinationDetector()
        same_evidence = "OpenAI is an AI safety company"
        fields = {
            "entityName": {
                "value": "OpenAI",
                "evidence": same_evidence,
                "confidence": 0.95,
            },
            "description": {
                "value": "AI safety",
                "evidence": same_evidence,
                "confidence": 0.90,
            },
            "industry": {
                "value": "AI",
                "evidence": same_evidence,
                "confidence": 0.85,
            },
        }
        report = detector.analyze_record(fields, SOURCE_TEXT)
        dup_flags = [
            f for f in report.flags if f.check_type == "duplicate_evidence"
        ]
        assert len(dup_flags) >= 1

    def test_two_fields_same_evidence_ok(self) -> None:
        """Only flag when 3+ fields share evidence."""
        detector = HallucinationDetector()
        same_evidence = "OpenAI is an AI safety company"
        fields = {
            "entityName": {
                "value": "OpenAI",
                "evidence": same_evidence,
                "confidence": 0.95,
            },
            "description": {
                "value": "AI safety",
                "evidence": same_evidence,
                "confidence": 0.90,
            },
        }
        report = detector.analyze_record(fields, SOURCE_TEXT)
        dup_flags = [
            f for f in report.flags if f.check_type == "duplicate_evidence"
        ]
        assert len(dup_flags) == 0

    def test_array_items_duplicate_evidence(self) -> None:
        detector = HallucinationDetector()
        same_evidence = "founded in 2015 by Sam Altman"
        fields = {
            "founders": [
                {"value": "Sam", "evidence": same_evidence, "confidence": 0.9},
                {"value": "Altman", "evidence": same_evidence, "confidence": 0.9},
                {"value": "Elon", "evidence": same_evidence, "confidence": 0.9},
            ],
        }
        report = detector.analyze_record(fields, SOURCE_TEXT)
        dup_flags = [
            f for f in report.flags if f.check_type == "duplicate_evidence"
        ]
        assert len(dup_flags) >= 1


class TestConfidenceUniformity:
    def test_varied_confidence_passes(self) -> None:
        detector = HallucinationDetector()
        report = detector.analyze_record(CLEAN_FIELDS, SOURCE_TEXT)
        unif_flags = [
            f for f in report.flags if f.check_type == "uniformity"
        ]
        assert len(unif_flags) == 0

    def test_all_same_confidence_flagged(self) -> None:
        detector = HallucinationDetector()
        fields = {
            "a": {"value": "OpenAI", "evidence": "OpenAI is", "confidence": 0.95},
            "b": {"value": "2015", "evidence": "founded in 2015", "confidence": 0.95},
            "c": {"value": "SF", "evidence": "San Francisco", "confidence": 0.95},
            "d": {"value": "AI", "evidence": "AI safety", "confidence": 0.95},
        }
        report = detector.analyze_record(fields, SOURCE_TEXT)
        unif_flags = [
            f for f in report.flags if f.check_type == "uniformity"
        ]
        assert len(unif_flags) >= 1

    def test_three_fields_not_flagged(self) -> None:
        """Need 4+ fields to detect uniformity."""
        detector = HallucinationDetector()
        fields = {
            "a": {"value": "OpenAI", "evidence": "OpenAI is", "confidence": 0.95},
            "b": {"value": "2015", "evidence": "founded in 2015", "confidence": 0.95},
            "c": {"value": "SF", "evidence": "San Francisco", "confidence": 0.95},
        }
        report = detector.analyze_record(fields, SOURCE_TEXT)
        unif_flags = [
            f for f in report.flags if f.check_type == "uniformity"
        ]
        assert len(unif_flags) == 0


class TestCompleteness:
    def test_complete_startup_passes(self) -> None:
        detector = HallucinationDetector()
        report = detector.analyze_record(
            CLEAN_FIELDS, SOURCE_TEXT, record_type="STARTUP",
        )
        comp_flags = [
            f for f in report.flags if f.check_type == "completeness"
        ]
        assert len(comp_flags) == 0

    def test_missing_required_field_flagged(self) -> None:
        detector = HallucinationDetector()
        fields = {
            "entityName": {
                "value": "OpenAI",
                "evidence": "OpenAI is",
                "confidence": 0.95,
            },
            # Missing "description"
        }
        report = detector.analyze_record(
            fields, SOURCE_TEXT, record_type="STARTUP",
        )
        comp_flags = [
            f for f in report.flags if f.check_type == "completeness"
        ]
        assert len(comp_flags) >= 1
        assert "description" in comp_flags[0].message

    def test_empty_value_counts_as_missing(self) -> None:
        detector = HallucinationDetector()
        fields = {
            "entityName": {
                "value": "OpenAI",
                "evidence": "OpenAI is",
                "confidence": 0.95,
            },
            "description": {
                "value": "",
                "evidence": "",
                "confidence": 0.0,
            },
        }
        report = detector.analyze_record(
            fields, SOURCE_TEXT, record_type="PRODUCT",
        )
        comp_flags = [
            f for f in report.flags if f.check_type == "completeness"
        ]
        assert len(comp_flags) >= 1

    def test_no_record_type_skips(self) -> None:
        detector = HallucinationDetector()
        report = detector.analyze_record({}, SOURCE_TEXT, record_type="")
        comp_flags = [
            f for f in report.flags if f.check_type == "completeness"
        ]
        assert len(comp_flags) == 0

    def test_unknown_record_type_skips(self) -> None:
        detector = HallucinationDetector()
        report = detector.analyze_record(
            {}, SOURCE_TEXT, record_type="UNKNOWN_TYPE",
        )
        comp_flags = [
            f for f in report.flags if f.check_type == "completeness"
        ]
        assert len(comp_flags) == 0

    def test_all_fields_missing_critical(self) -> None:
        """Missing 2+ required fields is critical severity."""
        detector = HallucinationDetector()
        report = detector.analyze_record(
            {}, SOURCE_TEXT, record_type="STARTUP",
        )
        comp_flags = [
            f for f in report.flags if f.check_type == "completeness"
        ]
        assert len(comp_flags) >= 1
        assert comp_flags[0].severity == "critical"


class TestURLFormat:
    def test_valid_url_passes(self) -> None:
        detector = HallucinationDetector()
        fields = {
            "website": {
                "value": "https://openai.com",
                "evidence": "Website: https://openai.com",
                "confidence": 0.99,
            },
        }
        report = detector.analyze_record(fields, SOURCE_TEXT)
        url_flags = [
            f for f in report.flags if f.check_type == "url_format"
        ]
        assert len(url_flags) == 0

    def test_missing_protocol_flagged(self) -> None:
        detector = HallucinationDetector()
        fields = {
            "website": {
                "value": "openai.com",
                "evidence": "Website: https://openai.com",
                "confidence": 0.90,
            },
        }
        report = detector.analyze_record(fields, SOURCE_TEXT)
        url_flags = [
            f for f in report.flags if f.check_type == "url_format"
        ]
        assert len(url_flags) >= 1
        assert "missing protocol" in url_flags[0].message.lower()

    def test_malformed_url_flagged(self) -> None:
        detector = HallucinationDetector()
        fields = {
            "website": {
                "value": "https://not a valid url with spaces",
                "evidence": "Website: https://openai.com",
                "confidence": 0.90,
            },
        }
        report = detector.analyze_record(fields, SOURCE_TEXT)
        url_flags = [
            f for f in report.flags if f.check_type == "url_format"
        ]
        assert len(url_flags) >= 1

    def test_non_url_field_skipped(self) -> None:
        detector = HallucinationDetector()
        fields = {
            "entityName": {
                "value": "not-a-url",
                "evidence": "OpenAI is",
                "confidence": 0.90,
            },
        }
        report = detector.analyze_record(fields, SOURCE_TEXT)
        url_flags = [
            f for f in report.flags if f.check_type == "url_format"
        ]
        assert len(url_flags) == 0

    def test_github_url_validated(self) -> None:
        detector = HallucinationDetector()
        fields = {
            "githubUrl": {
                "value": "https://github.com/openai/gpt-4",
                "evidence": "GitHub: https://github.com/openai/gpt-4",
                "confidence": 0.95,
            },
        }
        report = detector.analyze_record(fields, SOURCE_TEXT)
        url_flags = [
            f for f in report.flags if f.check_type == "url_format"
        ]
        assert len(url_flags) == 0


class TestStatisticalOutlier:
    def test_reasonable_funding_passes(self) -> None:
        detector = HallucinationDetector()
        fields = {
            "fundingTotal": {
                "value": "$11.3 billion",
                "evidence": "raised $11.3 billion",
                "confidence": 0.97,
            },
        }
        report = detector.analyze_record(fields, SOURCE_TEXT)
        outlier_flags = [
            f for f in report.flags if f.check_type == "outlier"
        ]
        assert len(outlier_flags) == 0

    def test_absurd_funding_flagged(self) -> None:
        detector = HallucinationDetector()
        fields = {
            "fundingTotal": {
                "value": "$999T",
                "evidence": "raised $11.3 billion",
                "confidence": 0.90,
            },
        }
        report = detector.analyze_record(fields, SOURCE_TEXT)
        outlier_flags = [
            f for f in report.flags if f.check_type == "outlier"
        ]
        assert len(outlier_flags) >= 1
        assert outlier_flags[0].severity == "critical"

    def test_negative_employees_flagged(self) -> None:
        detector = HallucinationDetector()
        fields = {
            "employeeCount": {
                "value": "-500",
                "evidence": "500 employees",
                "confidence": 0.90,
            },
        }
        report = detector.analyze_record(fields, SOURCE_TEXT)
        outlier_flags = [
            f for f in report.flags if f.check_type == "outlier"
        ]
        assert len(outlier_flags) >= 1

    def test_non_numeric_field_skipped(self) -> None:
        detector = HallucinationDetector()
        fields = {
            "entityName": {
                "value": "OpenAI",
                "evidence": "OpenAI is",
                "confidence": 0.95,
            },
        }
        report = detector.analyze_record(fields, SOURCE_TEXT)
        outlier_flags = [
            f for f in report.flags if f.check_type == "outlier"
        ]
        assert len(outlier_flags) == 0

    def test_non_numeric_value_skipped(self) -> None:
        detector = HallucinationDetector()
        fields = {
            "fundingTotal": {
                "value": "undisclosed",
                "evidence": "undisclosed funding",
                "confidence": 0.80,
            },
        }
        report = detector.analyze_record(fields, SOURCE_TEXT)
        outlier_flags = [
            f for f in report.flags if f.check_type == "outlier"
        ]
        assert len(outlier_flags) == 0

    def test_funding_with_suffix(self) -> None:
        detector = HallucinationDetector()
        fields = {
            "fundingTotal": {
                "value": "$50M",
                "evidence": "raised $50 million",
                "confidence": 0.95,
            },
        }
        report = detector.analyze_record(fields, SOURCE_TEXT)
        outlier_flags = [
            f for f in report.flags if f.check_type == "outlier"
        ]
        assert len(outlier_flags) == 0
