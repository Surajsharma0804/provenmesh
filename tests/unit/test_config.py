"""Tests for config/settings.py and config/constants.py."""
from __future__ import annotations

from provenmesh.config.constants import (
    COST_COUNTER_KEY,
    CRAWL_CONSUMER_GROUP,
    CRAWL_DLQ,
    DEDUP_KEY_PREFIX,
    DISCOVERY_STREAM,
    EXPORT_DLQ,
    EXPORT_STREAM,
    EXTRACTION_DLQ,
    EXTRACTION_STREAM,
    RAW_STORE_PREFIX,
    RESOLUTION_DLQ,
    RESOLUTION_STREAM,
    SCHEMA_VERSION,
    SHEETS_TAB_ORDER,
    USER_AGENTS,
)
from provenmesh.config.settings import Settings, get_settings


class TestConstants:
    def test_schema_version(self) -> None:
        assert SCHEMA_VERSION == "1.0"

    def test_stream_names(self) -> None:
        assert "provenmesh:" in DISCOVERY_STREAM
        assert "provenmesh:" in EXTRACTION_STREAM
        assert "provenmesh:" in RESOLUTION_STREAM
        assert "provenmesh:" in EXPORT_STREAM

    def test_dlq_streams(self) -> None:
        for dlq in [CRAWL_DLQ, EXTRACTION_DLQ, RESOLUTION_DLQ, EXPORT_DLQ]:
            assert "dlq" in dlq

    def test_user_agents(self) -> None:
        assert len(USER_AGENTS) >= 5
        for ua in USER_AGENTS:
            assert "Mozilla" in ua

    def test_sheets_tab_order(self) -> None:
        assert len(SHEETS_TAB_ORDER) == 6
        assert "Startups" in SHEETS_TAB_ORDER
        assert "Entity Mapping Log" in SHEETS_TAB_ORDER

    def test_redis_key_prefixes(self) -> None:
        assert DEDUP_KEY_PREFIX == "dedup"
        assert "cost" in COST_COUNTER_KEY

    def test_s3_prefix(self) -> None:
        assert RAW_STORE_PREFIX == "raw"

    def test_consumer_group(self) -> None:
        assert "crawl" in CRAWL_CONSUMER_GROUP


class TestSettings:
    def test_default_settings(self) -> None:
        s = Settings()
        assert s.app_env == "development"
        assert s.debug is False
        assert s.redis_url == "redis://localhost:6379/0"
        assert s.per_domain_rate_limit_rps == 1.0
        assert s.max_global_concurrency == 50
        assert s.grounding_threshold == 90

    def test_is_production(self) -> None:
        s = Settings()
        assert s.is_production is False

    def test_paths(self) -> None:
        s = Settings()
        assert s.configs_dir.name == "configs"
        assert s.schemas_dir.name == "schemas"

    def test_get_settings_cached(self) -> None:
        s1 = get_settings()
        s2 = get_settings()
        assert s1 is s2

    def test_queue_settings(self) -> None:
        s = Settings()
        assert s.queue_high_water_mark == 10_000
        assert s.queue_low_water_mark == 5_000
        assert s.backpressure_max_delay_seconds == 30

    def test_llm_settings(self) -> None:
        s = Settings()
        assert s.llm_daily_token_budget == 5_000_000
        assert s.retry_max_attempts == 5
