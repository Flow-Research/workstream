"""Application settings loaded from environment variables."""

from __future__ import annotations

import base64
import binascii
import json
import os
from collections.abc import Mapping
from functools import lru_cache
from pathlib import Path
from typing import Literal, Self

from dotenv import dotenv_values
from pydantic import Field, PrivateAttr, SecretStr, model_validator
from pydantic_settings import (
    BaseSettings,
    DotEnvSettingsSource,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
)


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
    token_issuer: str | None = None
    token_audience: str = "workstream"
    token_jwks_url: str | None = None
    token_algorithms: str = ""
    required_human_scope: str = "workstream:access"
    required_service_scope: str = "workstream:service"
    token_clock_skew_seconds: int = Field(default=30, ge=0, le=300)
    token_max_bytes: int = Field(default=16_384, ge=512, le=32_768)
    token_header_max_bytes: int = Field(default=4_096, ge=128, le=8_192)
    token_payload_max_bytes: int = Field(default=12_288, ge=256, le=24_576)
    token_jwks_cache_ttl_seconds: int = Field(default=300, ge=30, le=3_600)
    token_jwks_max_response_bytes: int = Field(default=262_144, ge=1_024, le=1_048_576)
    token_jwks_max_keys: int = Field(default=20, ge=1, le=100)
    token_unknown_kid_cache_ttl_seconds: int = Field(default=30, ge=1, le=300)
    token_unknown_kid_cache_max_entries: int = Field(default=100, ge=1, le=1_000)
    token_jwks_connect_timeout_seconds: float = Field(default=2.0, ge=0.1, le=10.0)
    token_jwks_read_timeout_seconds: float = Field(default=3.0, ge=0.1, le=10.0)
    token_jwks_write_timeout_seconds: float = Field(default=3.0, ge=0.1, le=10.0)
    token_jwks_pool_timeout_seconds: float = Field(default=1.0, ge=0.1, le=10.0)
    token_jwks_total_timeout_seconds: float = Field(default=5.0, ge=0.5, le=15.0)
    token_introspection_mode: Literal["disabled", "required"] | None = None
    token_introspection_disabled_reason: str | None = None
    token_introspection_url: str | None = None
    token_introspection_client_id: str | None = None
    token_introspection_client_secret: str | None = None
    token_introspection_max_response_bytes: int = Field(default=65_536, ge=256, le=262_144)
    token_introspection_connect_timeout_seconds: float = Field(default=2.0, ge=0.1, le=10.0)
    token_introspection_read_timeout_seconds: float = Field(default=3.0, ge=0.1, le=10.0)
    token_introspection_write_timeout_seconds: float = Field(default=3.0, ge=0.1, le=10.0)
    token_introspection_pool_timeout_seconds: float = Field(default=1.0, ge=0.1, le=10.0)
    token_introspection_total_timeout_seconds: float = Field(default=5.0, ge=0.5, le=15.0)
    project_agent_openai_agent_sdk_model: str | None = None
    project_agent_run_timeout_seconds: float = Field(default=1800.0, gt=0.0, le=7200.0)
    project_agent_max_prompt_bytes: int = Field(default=2_000_000, gt=0, le=10_000_000)
    project_setup_pipeline_autostart: bool = True
    celery_broker_url: str | None = None
    celery_result_backend_url: str | None = None
    celery_task_always_eager: bool = False
    actor_registry_refresh_interval_seconds: int = Field(default=300, ge=0, le=86_400)
    api_first_access_rate_limit: int = Field(default=10, ge=1, le=10_000)
    api_first_access_rate_window_seconds: int = Field(default=60, ge=1, le=3_600)
    api_admin_mutation_rate_limit: int = Field(default=30, ge=1, le=10_000)
    api_admin_mutation_rate_window_seconds: int = Field(default=60, ge=1, le=3_600)
    artifact_store_backend: Literal["disabled", "local", "s3_compatible"] = "disabled"
    artifact_local_root: Path | None = None
    artifact_maximum_bytes: int = Field(default=512 * 1024 * 1024, gt=0)
    artifact_stream_buffer_bytes: int = Field(default=1024 * 1024, gt=0, le=1024 * 1024)
    artifact_operation_lock_timeout_seconds: float = Field(
        default=1800.0,
        gt=0.0,
        le=7200.0,
    )
    artifact_scratch_root: Path | None = None
    artifact_scratch_aggregate_reserved_bytes: int = Field(
        default=4 * 512 * 1024 * 1024,
        ge=512 * 1024 * 1024,
    )
    artifact_scratch_maximum_files: int = Field(default=8, ge=1, le=1024)
    artifact_scratch_maximum_concurrency: int = Field(default=4, ge=1, le=1024)
    artifact_scratch_minimum_free_bytes: int = Field(
        default=512 * 1024 * 1024,
        ge=0,
    )
    artifact_scratch_reservation_ttl_seconds: float = Field(
        default=2400.0,
        gt=0.0,
        le=86_400.0,
    )
    artifact_preparation_total_deadline_seconds: float = Field(
        default=1800.0,
        gt=0.0,
        le=7200.0,
    )
    artifact_scratch_cleanup_margin_seconds: float = Field(
        default=300.0,
        gt=0.0,
        le=3600.0,
    )
    artifact_scratch_cleanup_interval_seconds: int = Field(
        default=300,
        gt=0,
        le=86_400,
    )

    model_config = SettingsConfigDict(
        env_prefix="WORKSTREAM_",
        env_file=".env",
        extra="ignore",
        hide_input_in_errors=True,
    )

    _api_rate_limit_key_secret: SecretStr | None = PrivateAttr(default=None)

    def __init__(self, **values: object) -> None:
        """Remove rate-control secret material before structured validation."""
        secret = _extract_api_rate_limit_key_secret(values)
        super().__init__(**values)
        self._api_rate_limit_key_secret = secret

    @classmethod
    def model_validate(cls, obj: object, **kwargs: object) -> Self:
        """Sanitize secret-bearing mappings before Pydantic retains input."""
        if isinstance(obj, Mapping) and "api_rate_limit_key_secret" in obj:
            sanitized = dict(obj)
            secret = _extract_api_rate_limit_key_secret(sanitized)
            sanitized["api_rate_limit_key_secret"] = None
            settings = super().model_validate(sanitized, **kwargs)
            settings._api_rate_limit_key_secret = secret
            return settings
        return super().model_validate(obj, **kwargs)

    @classmethod
    def model_validate_json(
        cls,
        json_data: str | bytes | bytearray,
        **kwargs: object,
    ) -> Self:
        """Sanitize JSON secret input before Pydantic retains the document."""
        malformed = False
        try:
            parsed = json.loads(json_data)
        except (json.JSONDecodeError, UnicodeDecodeError):
            malformed = True
            parsed = None
        if malformed:
            raise ValueError("invalid settings JSON")
        if isinstance(parsed, Mapping) and "api_rate_limit_key_secret" in parsed:
            return cls.model_validate(parsed, **kwargs)
        return super().model_validate_json(json_data, **kwargs)

    @classmethod
    def model_validate_strings(cls, obj: object, **kwargs: object) -> Self:
        """Sanitize string-mapping secret input before structured validation."""
        if isinstance(obj, Mapping) and "api_rate_limit_key_secret" in obj:
            sanitized = dict(obj)
            secret = _extract_api_rate_limit_key_secret(sanitized)
            sanitized["api_rate_limit_key_secret"] = None
            settings = super().model_validate_strings(sanitized, **kwargs)
            settings._api_rate_limit_key_secret = secret
            return settings
        return super().model_validate_strings(obj, **kwargs)

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        """Keep the manually resolved rate key out of dotenv validation input."""
        if isinstance(dotenv_settings, DotEnvSettingsSource):
            dotenv_settings.env_vars.pop("workstream_api_rate_limit_key_secret", None)
        return init_settings, env_settings, dotenv_settings, file_secret_settings

    @property
    def api_rate_limit_key_secret(self) -> SecretStr | None:
        """Return the validated, redacted rate-control key setting."""
        return self._api_rate_limit_key_secret

    @model_validator(mode="after")
    def validate_artifact_storage(self) -> Settings:
        """Reject unsafe or incomplete artifact-storage combinations.

        Returns:
            Validated settings instance.

        Raises:
            ValueError: If enabled artifact storage is unsafe or incomplete.
        """
        if self.artifact_scratch_maximum_concurrency > self.artifact_scratch_maximum_files:
            raise ValueError("artifact scratch concurrency cannot exceed its file limit")
        if (
            self.artifact_preparation_total_deadline_seconds
            + self.artifact_scratch_cleanup_margin_seconds
            >= self.artifact_scratch_reservation_ttl_seconds
        ):
            raise ValueError("artifact preparation deadline must expire before scratch TTL")
        if self.artifact_scratch_root is not None and self.artifact_local_root is not None:
            scratch_root = self.artifact_scratch_root.resolve(strict=False)
            local_root = self.artifact_local_root.resolve(strict=False)
            if (
                scratch_root == local_root
                or scratch_root.is_relative_to(local_root)
                or local_root.is_relative_to(scratch_root)
            ):
                raise ValueError(
                    "artifact scratch and durable local storage roots must be separate"
                )
        if self.artifact_store_backend == "disabled":
            return self
        if self.artifact_scratch_root is None:
            raise ValueError("enabled artifact storage requires an artifact scratch root")
        if self.artifact_store_backend == "local":
            if self.environment not in {"local", "dev", "development", "test"}:
                raise ValueError("local artifact storage is restricted to development and test")
            if self.artifact_local_root is None:
                raise ValueError("local artifact storage requires an artifact root")
        return self


@lru_cache
def get_settings() -> Settings:
    """Load and cache application settings.

    Returns:
        Settings resolved from environment variables and optional ``.env``.
    """
    return Settings()


def _extract_api_rate_limit_key_secret(values: dict[str, object]) -> SecretStr | None:
    """Resolve and validate the key without entering Pydantic's input graph."""
    missing = object()
    raw_value = values.pop("api_rate_limit_key_secret", missing)
    if raw_value is missing:
        raw_value = os.environ.get("WORKSTREAM_API_RATE_LIMIT_KEY_SECRET", missing)
    if raw_value is missing:
        env_file = values.get("_env_file", ".env")
        if env_file is not None:
            env_encoding = values.get("_env_file_encoding", "utf-8")
            env_files = (env_file,) if isinstance(env_file, (str, os.PathLike)) else tuple(env_file)
            for path in env_files:
                dotenv = dotenv_values(path, encoding=env_encoding)
                raw_value = dotenv.get("WORKSTREAM_API_RATE_LIMIT_KEY_SECRET", raw_value)
    if raw_value is missing or raw_value is None:
        return None
    if isinstance(raw_value, SecretStr):
        secret = raw_value
    elif isinstance(raw_value, str):
        secret = SecretStr(raw_value)
    else:
        raise ValueError("invalid API rate limit key secret")
    decode_api_rate_limit_key_secret(secret)
    return secret


def decode_api_rate_limit_key_secret(value: SecretStr) -> bytes:
    """Decode one canonical padded Base64 rate-control key."""
    secret = value.get_secret_value()
    if not secret.isascii():
        raise ValueError("invalid API rate limit key secret")
    invalid = False
    try:
        encoded = secret.encode("ascii")
        decoded = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError):
        invalid = True
        encoded = b""
        decoded = b""
    if invalid:
        raise ValueError("invalid API rate limit key secret")
    if not 32 <= len(decoded) <= 64 or base64.b64encode(decoded) != encoded:
        raise ValueError("invalid API rate limit key secret")
    return decoded
