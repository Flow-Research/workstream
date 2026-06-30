"""Application settings loaded from environment variables."""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration for the Workstream API."""

    app_name: str = "Workstream API"
    app_version: str = "0.1.0"
    debug: bool = False
    environment: Literal[
        "local",
        "dev",
        "development",
        "test",
        "staging",
        "preview",
        "prod",
        "production",
    ] = "production"
    auth_provider: Literal["dev", "flow"] = "flow"
    database_url: str | None = None
    dev_auth_token: str | None = None
    dev_auth_subject: str | None = None
    dev_auth_issuer: str | None = None
    dev_auth_email: str | None = None
    dev_auth_display_name: str | None = None
    dev_auth_roles: str = ""
    flow_auth_issuer: str = "https://auth.flow.local"
    flow_auth_audience: str = "workstream-api"
    flow_auth_local_hmac_secret: str | None = None
    enable_demo_routes: bool = False
    project_agent_runtime: Literal["deterministic", "openai"] = "deterministic"
    openai_agent_model: str | None = None

    model_config = SettingsConfigDict(
        env_prefix="WORKSTREAM_",
        env_file=".env",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    """Load and cache application settings.

    Returns:
        Settings resolved from environment variables and optional ``.env``.
    """
    return Settings()
