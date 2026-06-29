"""
PHANTOM Configuration
Pydantic Settings-based configuration with environment variable support.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class PhantomSettings(BaseSettings):
    """Central configuration for PHANTOM. All values can be overridden via environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── API ──────────────────────────────────────────────────────────────────
    phantom_api_url: str = Field(
        default="http://localhost:8001",
        description="Base URL of the PHANTOM FastAPI service",
    )
    phantom_api_key: Optional[str] = Field(
        default=None,
        description="Optional API key for protected deployments",
    )
    api_host: str = Field(default="0.0.0.0", description="API listen host")
    api_port: int = Field(default=8001, description="API listen port")

    # ── Redis ────────────────────────────────────────────────────────────────
    redis_url: str = Field(
        default="redis://localhost:6379/1",
        description="Redis connection URL for result caching",
    )
    cache_ttl_seconds: int = Field(
        default=3600,
        description="Default TTL for cached results (seconds)",
    )

    # ── Concurrency ──────────────────────────────────────────────────────────
    max_concurrent_tasks: int = Field(
        default=3,
        ge=1,
        le=20,
        description="Maximum number of concurrent browser tasks",
    )

    # ── Browser ──────────────────────────────────────────────────────────────
    browser_headless: bool = Field(
        default=True,
        description="Run browser in headless mode",
    )
    default_timeout_ms: int = Field(
        default=30_000,
        ge=1000,
        le=120_000,
        description="Default page navigation timeout in milliseconds",
    )
    screenshot_dir: Path = Field(
        default=Path("./screenshots"),
        description="Directory for storing screenshots",
    )

    # ── Stealth ──────────────────────────────────────────────────────────────
    rate_limit_delay_ms: int = Field(
        default=1500,
        ge=0,
        description="Minimum delay between requests in milliseconds",
    )
    user_agent_rotation: bool = Field(
        default=True,
        description="Enable random User-Agent rotation",
    )
    proxy_url: Optional[str] = Field(
        default=None,
        description="Optional proxy URL (http://user:pass@host:port)",
    )

    # ── Logging ──────────────────────────────────────────────────────────────
    log_level: str = Field(
        default="INFO",
        description="Logging level (DEBUG, INFO, WARNING, ERROR)",
    )

    # ── Retry ────────────────────────────────────────────────────────────────
    max_retries: int = Field(
        default=3,
        ge=0,
        le=10,
        description="Maximum retry attempts per task",
    )
    retry_backoff_base_ms: int = Field(
        default=2000,
        description="Base delay for exponential backoff (milliseconds)",
    )

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        allowed = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        upper = v.upper()
        if upper not in allowed:
            raise ValueError(f"log_level must be one of {allowed}")
        return upper

    @field_validator("screenshot_dir")
    @classmethod
    def ensure_screenshot_dir(cls, v: Path) -> Path:
        v.mkdir(parents=True, exist_ok=True)
        return v


# Singleton settings instance
settings = PhantomSettings()
