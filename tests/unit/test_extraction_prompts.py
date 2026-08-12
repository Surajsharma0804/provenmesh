"""Tests for extraction/prompts.py — prompt registry completeness."""
from __future__ import annotations

from provenmesh.extraction.prompts import (
    EXTRACTION_PROMPTS,
    JOB_PROMPT,
    NEWS_PROMPT,
    PAPER_PROMPT,
    PRODUCT_PROMPT,
    STARTUP_PROMPT,
    SYSTEM_PROMPT,
)


class TestPrompts:
    def test_system_prompt_exists(self) -> None:
        assert len(SYSTEM_PROMPT) > 100
        assert "evidence" in SYSTEM_PROMPT.lower()
        assert "confidence" in SYSTEM_PROMPT.lower()

    def test_all_record_types_in_registry(self) -> None:
        assert "STARTUP" in EXTRACTION_PROMPTS
        assert "PRODUCT" in EXTRACTION_PROMPTS
        assert "PAPER" in EXTRACTION_PROMPTS
        assert "JOB" in EXTRACTION_PROMPTS
        assert "NEWS_SIGNAL" in EXTRACTION_PROMPTS

    def test_startup_prompt_has_content_placeholder(self) -> None:
        assert "{content}" in STARTUP_PROMPT

    def test_product_prompt_has_content_placeholder(self) -> None:
        assert "{content}" in PRODUCT_PROMPT

    def test_paper_prompt_has_content_placeholder(self) -> None:
        assert "{content}" in PAPER_PROMPT

    def test_job_prompt_has_content_placeholder(self) -> None:
        assert "{content}" in JOB_PROMPT

    def test_news_prompt_has_content_placeholder(self) -> None:
        assert "{content}" in NEWS_PROMPT

    def test_prompts_require_evidence(self) -> None:
        for name, prompt in EXTRACTION_PROMPTS.items():
            assert "evidence" in prompt.lower(), f"{name} missing evidence"

    def test_prompts_require_confidence(self) -> None:
        for name, prompt in EXTRACTION_PROMPTS.items():
            assert "confidence" in prompt.lower(), f"{name} missing confidence"

    def test_prompt_formatting(self) -> None:
        formatted = STARTUP_PROMPT.replace("{content}", "Test HTML content")
        assert "Test HTML content" in formatted

