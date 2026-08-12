"""Runtime settings with conservative transport defaults."""

from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="GA4GH_HARNESS_", extra="ignore")

    profile_version: str = "0.1.0"
    registry_base_url: str = "https://implementation-registry.ga4gh.org/api"
    registry_cache_ttl_seconds: float = 300.0
    connect_timeout_seconds: float = 5.0
    read_timeout_seconds: float = 20.0
    retry_backoff_seconds: float = 0.25
    max_retries: int = 2
    max_redirects: int = 3
    max_response_bytes: int = 5_000_000
    verify_tls: bool = True
    allow_http: bool = False
    allow_private_hosts: bool = False
    allowed_hosts: list[str] = Field(default_factory=list)
    user_agent: str = "ga4gh-agentic-harness/0.1"
    ledger_path: Path = Path(".ga4gh-harness-runs.db")
    trace_path: Path | None = None
