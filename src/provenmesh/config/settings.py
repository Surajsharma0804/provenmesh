"""Application settings — loaded from environment variables via pydantic-settings.

Secrets are loaded from .env (gitignored), never hardcoded (PDF §10.3).
Every operational threshold is configurable without code changes.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

# Project root — two levels up from src/provenmesh/config/
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent


class Settings(BaseSettings):
    """Central configuration — single source for all runtime settings."""

    model_config = SettingsConfigDict(
        env_file=str(PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ─── Application ─────────────────────────────────────────────
    app_env: str = "development"
    debug: bool = False

    # ─── Infrastructure ──────────────────────────────────────────
    redis_url: str = "redis://localhost:6379/0"
    postgres_dsn: str = "postgresql+asyncpg://provenmesh:provenmesh_dev@localhost:5432/provenmesh"
    s3_endpoint: str = "http://localhost:9000"
    s3_bucket: str = "provenmesh-raw"
    s3_access_key: str = "provenmesh"
    s3_secret_key: SecretStr = SecretStr("provenmesh_dev")
    s3_region: str = "us-east-1"

    # ─── LLM Providers ──────────────────────────────────────────
    gemini_api_key: SecretStr = SecretStr("")
    groq_api_key: SecretStr = SecretStr("")
    deepseek_api_key: SecretStr = SecretStr("")

    # ─── GitHub ──────────────────────────────────────────────────
    github_token: SecretStr = SecretStr("")

    # ─── Proxy ───────────────────────────────────────────────────
    proxy_pool_url: str = ""

    # ─── Google Sheets ───────────────────────────────────────────
    google_sheets_credentials_json: str = ""
    google_sheets_spreadsheet_id: str = ""

    # ─── LLM Cost Governance (PDF §5.4) ─────────────────────────
    llm_daily_token_budget: int = 5_000_000
    llm_warning_threshold_pct: int = 80
    llm_halt_threshold_pct: int = 100
    llm_cache_ttl_seconds: int = 86400

    # ─── Crawling (PDF §3.1, §7) ────────────────────────────────
    per_domain_rate_limit_rps: float = 1.0
    max_domain_concurrency: int = 5
    max_global_concurrency: int = 50
    max_fetch_retries: int = 5
    fetch_timeout_seconds: int = 30

    # ─── Entity Resolution (PDF §6) ─────────────────────────────
    grounding_threshold: int = 90
    fuzzy_threshold: int = 85
    embedding_accept_threshold: float = 0.88
    review_threshold: float = 0.75

    # ─── Deduplication (PDF §4.3) ────────────────────────────────
    dedup_ttl_seconds: int = 2_592_000  # 30 days

    # ─── Workers ─────────────────────────────────────────────────
    worker_max_items_before_recycle: int = 1000
    worker_health_check_port: int = 8080
    worker_shutdown_timeout_seconds: int = 30
    poison_message_max_idle_ms: int = 300_000  # 5 minutes

    # ─── Backpressure (v2 §1) ───────────────────────────────────
    queue_high_water_mark: int = 10_000
    queue_low_water_mark: int = 5_000
    backpressure_max_delay_seconds: int = 30

    # ─── Circuit Breaker (PDF §5.1) ─────────────────────────────
    circuit_breaker_failure_threshold: int = 5
    circuit_breaker_recovery_timeout_seconds: int = 60

    # ─── Retry ──────────────────────────────────────────────────
    retry_max_attempts: int = 5
    retry_base_delay_seconds: float = 1.0
    retry_max_delay_seconds: float = 60.0
    retry_jitter_max_seconds: float = 1.5

    # ─── Export ─────────────────────────────────────────────────
    export_batch_size: int = 500
    export_max_rows_per_tab: int = 50_000

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def configs_dir(self) -> Path:
        return PROJECT_ROOT / "configs"

    @property
    def schemas_dir(self) -> Path:
        return PROJECT_ROOT / "schemas"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Singleton settings instance — cached after first creation."""
    return Settings()
