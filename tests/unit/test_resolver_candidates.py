"""Tests for resolver/candidates.py — CandidateIndex for efficient pre-filtering."""
from __future__ import annotations

from provenmesh.resolver.candidates import CandidateIndex


class TestCandidateIndex:
    def test_empty_index(self) -> None:
        idx = CandidateIndex()
        assert idx.total_indexed == 0
        assert idx.get_candidates("test") == set()

    def test_add_and_retrieve(self) -> None:
        idx = CandidateIndex()
        idx.add("startup_openai", "OpenAI")
        assert idx.total_indexed == 1
        candidates = idx.get_candidates("OpenAI")
        assert "startup_openai" in candidates

    def test_prefix_matching(self) -> None:
        idx = CandidateIndex()
        idx.add("startup_openai", "OpenAI")
        idx.add("startup_opentext", "OpenText")
        idx.add("startup_other", "Microsoft")
        # Both start with "ope"
        candidates = idx.get_candidates("Open")
        assert "startup_openai" in candidates
        assert "startup_opentext" in candidates

    def test_token_matching(self) -> None:
        idx = CandidateIndex()
        idx.add("startup_openai", "OpenAI Research")
        idx.add("startup_meta", "Meta AI Research")
        # Token "research" should match both
        candidates = idx.get_candidates("Research Lab")
        assert "startup_openai" in candidates
        assert "startup_meta" in candidates

    def test_short_name_fallback(self) -> None:
        idx = CandidateIndex()
        idx.add("startup_ai", "AI")
        # Short query (< 3 chars) falls back to all IDs
        candidates = idx.get_candidates("AI")
        assert len(candidates) >= 1

    def test_max_candidates_cap(self) -> None:
        idx = CandidateIndex()
        for i in range(100):
            idx.add(f"startup_{i}", f"OpenCompany{i}")
        candidates = idx.get_candidates("OpenCompany", max_candidates=10)
        assert len(candidates) <= 10

    def test_clear(self) -> None:
        idx = CandidateIndex()
        idx.add("startup_openai", "OpenAI")
        idx.clear()
        assert idx.total_indexed == 0
        assert idx.get_candidates("OpenAI") == set()

    def test_multiple_tokens(self) -> None:
        idx = CandidateIndex()
        idx.add("product_chatgpt", "ChatGPT Plus")
        candidates = idx.get_candidates("ChatGPT")
        assert "product_chatgpt" in candidates
