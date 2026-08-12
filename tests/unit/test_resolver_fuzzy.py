"""Tests for resolver/fuzzy.py — RapidFuzz-based entity matching."""
from __future__ import annotations

from provenmesh.resolver.fuzzy import (
    FuzzyMatch,
    fuzzy_match_batch,
    fuzzy_match_single,
    is_fuzzy_match,
)


class TestFuzzyMatchSingle:
    def test_identical(self) -> None:
        score = fuzzy_match_single("OpenAI", "OpenAI")
        assert score == 100.0

    def test_reordered(self) -> None:
        score = fuzzy_match_single("Sam Altman", "Altman Sam")
        assert score >= 90

    def test_case_insensitive(self) -> None:
        score = fuzzy_match_single("openai", "OPENAI")
        assert score == 100.0

    def test_different_names(self) -> None:
        score = fuzzy_match_single("OpenAI", "Microsoft")
        assert score < 50


class TestFuzzyMatchBatch:
    def test_basic_batch(self) -> None:
        candidates = {
            "startup_openai": "OpenAI",
            "startup_anthropic": "Anthropic",
            "startup_google": "Google",
        }
        matches = fuzzy_match_batch("OpenAI", candidates)
        assert len(matches) >= 1
        assert matches[0].canonical_id == "startup_openai"
        assert matches[0].score >= 90

    def test_empty_query(self) -> None:
        assert fuzzy_match_batch("", {"a": "b"}) == []

    def test_empty_candidates(self) -> None:
        assert fuzzy_match_batch("test", {}) == []

    def test_limit(self) -> None:
        candidates = {f"id_{i}": f"Company{i}" for i in range(20)}
        matches = fuzzy_match_batch("Company1", candidates, limit=3)
        assert len(matches) <= 3

    def test_threshold(self) -> None:
        candidates = {"a": "OpenAI", "b": "Microsoft"}
        matches = fuzzy_match_batch("OpenAI", candidates, threshold=95)
        # Only OpenAI should match at 95 threshold
        assert all(m.score >= 95 for m in matches)

    def test_sorted_by_score(self) -> None:
        candidates = {
            "a": "OpenAI Inc",
            "b": "OpenAI",
            "c": "Totally Different",
        }
        matches = fuzzy_match_batch("OpenAI", candidates, threshold=50)
        for i in range(len(matches) - 1):
            assert matches[i].score >= matches[i + 1].score


class TestIsFuzzyMatch:
    def test_match(self) -> None:
        # Identical strings should match
        assert is_fuzzy_match("OpenAI", "OpenAI") is True

    def test_no_match(self) -> None:
        assert is_fuzzy_match("OpenAI", "Microsoft") is False

    def test_custom_threshold(self) -> None:
        assert is_fuzzy_match("Open AI", "OpenAI", threshold=50) is True


class TestFuzzyMatch:
    def test_frozen(self) -> None:
        m = FuzzyMatch(
            matched_name="OpenAI", canonical_id="startup_openai",
            score=100.0, method="fuzzy",
        )
        assert m.matched_name == "OpenAI"
        assert m.method == "fuzzy"
