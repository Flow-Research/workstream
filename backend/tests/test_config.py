from __future__ import annotations

import base64
import json
from collections.abc import Mapping
from pathlib import Path
from typing import get_args

import pytest
from pydantic import SecretStr, ValidationError
from pydantic_settings import BaseSettings

from app.adapters.artifacts import create_artifact_store_bootstrap
from app.adapters.auth.flow import FlowAuthVerifier
from app.api.deps.auth import get_application_auth_verifier
from app.core.auth import clear_auth_verifier_cache, get_auth_verifier
from app.core.config import Settings, get_settings
from app.interfaces.external_services import (
    ExternalServiceConfigurationError,
    UnknownExternalServiceProviderError,
)
from app.main import create_app


def _assert_secret_not_retained(value: object, secret: str, seen: set[int] | None = None) -> None:
    """Assert a secret is unreachable through an error's public object graph."""
    if seen is None:
        seen = set()
    if id(value) in seen:
        return
    seen.add(id(value))
    if isinstance(value, str):
        assert secret not in value
    elif isinstance(value, SecretStr):
        assert value.get_secret_value() != secret
    elif isinstance(value, BaseException):
        if isinstance(value, ValidationError):
            _assert_secret_not_retained(value.errors(), secret, seen)
        _assert_secret_not_retained(value.args, secret, seen)
        _assert_secret_not_retained(vars(value), secret, seen)
        _assert_secret_not_retained(value.__cause__, secret, seen)
        _assert_secret_not_retained(value.__context__, secret, seen)
    elif isinstance(value, Mapping):
        for key, item in value.items():
            _assert_secret_not_retained(key, secret, seen)
            _assert_secret_not_retained(item, secret, seen)
    elif isinstance(value, (list, tuple, set)):
        for item in value:
            _assert_secret_not_retained(item, secret, seen)


def test_default_settings_are_fail_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("WORKSTREAM_DATABASE_URL", raising=False)
    monkeypatch.delenv("WORKSTREAM_DEV_AUTH_TOKEN", raising=False)
    monkeypatch.delenv("WORKSTREAM_API_RATE_LIMIT_KEY_SECRET", raising=False)

    settings = Settings()

    assert settings.app_name == "Workstream API"
    assert settings.environment == "production"
    assert settings.auth_provider == "flow"
    assert settings.database_url is None
    assert settings.dev_auth_token is None
    assert settings.api_rate_limit_key_secret is None
    assert settings.api_first_access_rate_limit == 10
    assert settings.api_first_access_rate_window_seconds == 60
    assert settings.api_admin_mutation_rate_limit == 30
    assert settings.api_admin_mutation_rate_window_seconds == 60


def test_rate_limit_secret_is_canonical_and_redacted() -> None:
    encoded = base64.b64encode(bytes(range(32))).decode("ascii")
    settings = Settings(api_rate_limit_key_secret=encoded)

    assert settings.api_rate_limit_key_secret is not None
    assert settings.api_rate_limit_key_secret.get_secret_value() == encoded
    assert encoded not in repr(settings)
    assert "api_rate_limit_key_secret" not in settings.model_dump()


def test_rate_limit_secret_loads_from_environment_and_dotenv(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    env_encoded = base64.b64encode(bytes(range(32))).decode("ascii")
    dotenv_encoded = base64.b64encode(bytes(range(1, 33))).decode("ascii")
    (tmp_path / ".env").write_text(
        f"WORKSTREAM_API_RATE_LIMIT_KEY_SECRET={dotenv_encoded}\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("WORKSTREAM_API_RATE_LIMIT_KEY_SECRET", env_encoded)

    env_settings = Settings()
    monkeypatch.delenv("WORKSTREAM_API_RATE_LIMIT_KEY_SECRET")
    dotenv_settings = Settings()

    assert env_settings.api_rate_limit_key_secret is not None
    assert env_settings.api_rate_limit_key_secret.get_secret_value() == env_encoded
    assert dotenv_settings.api_rate_limit_key_secret is not None
    assert dotenv_settings.api_rate_limit_key_secret.get_secret_value() == dotenv_encoded


def test_rate_limit_secret_loads_from_layered_dotenv_files(tmp_path: Path) -> None:
    first_encoded = base64.b64encode(bytes(range(32))).decode("ascii")
    second_encoded = base64.b64encode(bytes(range(1, 33))).decode("ascii")
    first = tmp_path / "first.env"
    second = tmp_path / "second.env"
    first.write_text(
        f"WORKSTREAM_API_RATE_LIMIT_KEY_SECRET={first_encoded}\n",
        encoding="utf-8",
    )
    second.write_text(
        f"WORKSTREAM_API_RATE_LIMIT_KEY_SECRET={second_encoded}\n",
        encoding="utf-8",
    )

    settings = Settings(_env_file=(first, second))

    assert settings.api_rate_limit_key_secret is not None
    assert settings.api_rate_limit_key_secret.get_secret_value() == second_encoded


def test_rate_limit_secret_is_absent_from_unrelated_structured_errors() -> None:
    encoded = base64.b64encode(bytes(range(32))).decode("ascii")

    with pytest.raises(ValidationError) as caught:
        Settings(
            api_rate_limit_key_secret=encoded,
            artifact_store_backend="flow_node",
        )

    assert encoded not in repr(caught.value.errors())
    assert encoded not in caught.value.json()
    _assert_secret_not_retained(caught.value, encoded)


def test_environment_rate_limit_secret_is_absent_from_unrelated_structured_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    encoded = base64.b64encode(bytes(range(32))).decode("ascii")
    monkeypatch.setenv("WORKSTREAM_API_RATE_LIMIT_KEY_SECRET", encoded)

    with pytest.raises(ValidationError) as caught:
        Settings(artifact_store_backend="flow_node")

    assert encoded not in repr(caught.value.errors())
    assert encoded not in caught.value.json()
    _assert_secret_not_retained(caught.value, encoded)


def test_dotenv_rate_limit_secret_is_absent_from_unrelated_structured_errors(
    tmp_path: Path,
) -> None:
    encoded = base64.b64encode(bytes(range(32))).decode("ascii")
    env_file = tmp_path / ".env"
    env_file.write_text(
        f"WORKSTREAM_API_RATE_LIMIT_KEY_SECRET={encoded}\n",
        encoding="utf-8",
    )

    with pytest.raises(ValidationError) as caught:
        Settings(_env_file=env_file, artifact_store_backend="flow_node")

    assert encoded not in repr(caught.value.errors())
    assert encoded not in caught.value.json()
    _assert_secret_not_retained(caught.value, encoded)


def test_model_validate_rejects_rate_limit_secret_without_structured_echo() -> None:
    invalid = "not-a-canonical-secret"

    with pytest.raises(ValueError, match="^invalid API rate limit key secret$") as caught:
        Settings.model_validate({"api_rate_limit_key_secret": invalid})

    assert not isinstance(caught.value, ValidationError)
    assert invalid not in f"{caught.value!s} {caught.value!r}"
    _assert_secret_not_retained(caught.value, invalid)


def test_model_validate_rate_limit_secret_is_absent_from_unrelated_errors() -> None:
    encoded = base64.b64encode(bytes(range(32))).decode("ascii")

    with pytest.raises(ValidationError) as caught:
        Settings.model_validate(
            {
                "api_rate_limit_key_secret": encoded,
                "artifact_store_backend": "flow_node",
            }
        )

    assert encoded not in repr(caught.value.errors())
    assert encoded not in caught.value.json()
    _assert_secret_not_retained(caught.value, encoded)


@pytest.mark.parametrize(
    ("method_name", "base_method_name"),
    [
        ("model_validate", "model_validate"),
        ("model_validate_json", "model_validate"),
        ("model_validate_strings", "model_validate_strings"),
    ],
)
def test_alternate_validation_never_passes_secret_into_pydantic(
    monkeypatch: pytest.MonkeyPatch,
    method_name: str,
    base_method_name: str,
) -> None:
    encoded = base64.b64encode(bytes(range(32))).decode("ascii")
    observed: dict[str, object] = {}

    class PydanticBoundaryReached(Exception):
        pass

    def capture_input(
        cls: type[BaseSettings],
        obj: object,
        **kwargs: object,
    ) -> BaseSettings:
        observed["input"] = obj
        raise PydanticBoundaryReached

    monkeypatch.setattr(BaseSettings, base_method_name, classmethod(capture_input))
    payload = {"api_rate_limit_key_secret": encoded}
    method = getattr(Settings, method_name)

    with pytest.raises(PydanticBoundaryReached):
        method(json.dumps(payload) if method_name.endswith("json") else payload)

    assert isinstance(observed["input"], Mapping)
    assert observed["input"]["api_rate_limit_key_secret"] is None
    _assert_secret_not_retained(observed, encoded)


@pytest.mark.parametrize("method_name", ["model_validate_json", "model_validate_strings"])
def test_alternate_validation_loads_rate_limit_secret(method_name: str) -> None:
    encoded = base64.b64encode(bytes(range(32))).decode("ascii")
    payload = {"api_rate_limit_key_secret": encoded}
    method = getattr(Settings, method_name)

    settings = method(json.dumps(payload) if method_name.endswith("json") else payload)

    assert settings.api_rate_limit_key_secret is not None
    assert settings.api_rate_limit_key_secret.get_secret_value() == encoded


@pytest.mark.parametrize("method_name", ["model_validate_json", "model_validate_strings"])
def test_alternate_validation_rejects_rate_limit_secret_without_echo(
    method_name: str,
) -> None:
    invalid = "not-a-canonical-secret"
    payload = {"api_rate_limit_key_secret": invalid}
    method = getattr(Settings, method_name)

    with pytest.raises(ValueError, match="^invalid API rate limit key secret$") as caught:
        method(json.dumps(payload) if method_name.endswith("json") else payload)

    assert not isinstance(caught.value, ValidationError)
    assert invalid not in f"{caught.value!s} {caught.value!r}"
    _assert_secret_not_retained(caught.value, invalid)


@pytest.mark.parametrize("method_name", ["model_validate_json", "model_validate_strings"])
def test_alternate_validation_secret_is_absent_from_unrelated_errors(
    method_name: str,
) -> None:
    encoded = base64.b64encode(bytes(range(32))).decode("ascii")
    payload = {
        "api_rate_limit_key_secret": encoded,
        "artifact_store_backend": "flow_node",
    }
    method = getattr(Settings, method_name)

    with pytest.raises(ValidationError) as caught:
        method(json.dumps(payload) if method_name.endswith("json") else payload)

    assert encoded not in repr(caught.value.errors())
    assert encoded not in caught.value.json()
    _assert_secret_not_retained(caught.value, encoded)


def test_model_validate_json_rejects_malformed_document_without_echo() -> None:
    invalid = "not-a-canonical-secret"
    payload = f'{{"api_rate_limit_key_secret":"{invalid}"'

    with pytest.raises(ValueError, match="^invalid settings JSON$") as caught:
        Settings.model_validate_json(payload)

    assert not isinstance(caught.value, ValidationError)
    assert invalid not in f"{caught.value!s} {caught.value!r}"
    assert caught.value.__cause__ is None
    assert caught.value.__context__ is None
    _assert_secret_not_retained(caught.value, invalid)


@pytest.mark.parametrize(
    "value",
    [
        "",
        " ",
        "AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8=\n",
        "AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8",
        base64.b64encode(bytes(31)).decode("ascii"),
        base64.b64encode(bytes(65)).decode("ascii"),
        "\u00e9" * 44,
    ],
)
def test_rate_limit_secret_rejects_invalid_values_without_echo(value: str) -> None:
    with pytest.raises(ValueError, match="^invalid API rate limit key secret$") as caught:
        Settings(api_rate_limit_key_secret=value)
    assert not isinstance(caught.value, ValidationError)
    rendered = f"{caught.value!s} {caught.value!r}"
    assert not hasattr(caught.value, "errors")
    assert not hasattr(caught.value, "json")
    if value.strip():
        assert value not in rendered
        _assert_secret_not_retained(caught.value, value)


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("api_first_access_rate_limit", 0),
        ("api_first_access_rate_limit", 10_001),
        ("api_admin_mutation_rate_limit", 0),
        ("api_admin_mutation_rate_limit", 10_001),
        ("api_first_access_rate_window_seconds", 0),
        ("api_first_access_rate_window_seconds", 3_601),
        ("api_admin_mutation_rate_window_seconds", 0),
        ("api_admin_mutation_rate_window_seconds", 3_601),
    ],
)
def test_rate_limit_numeric_bounds_are_enforced(field_name: str, value: int) -> None:
    with pytest.raises(ValidationError):
        Settings(**{field_name: value})


def test_settings_reject_unknown_environment() -> None:
    with pytest.raises(ValidationError):
        Settings(environment="unknown")


def _flow_settings(**overrides) -> Settings:
    values = {
        "environment": "test",
        "auth_provider": "flow",
        "token_issuer": "https://issuer.example.test",
        "token_jwks_url": "https://issuer.example.test/jwks",
        "token_algorithms": "RS256",
        "token_introspection_mode": "disabled",
        "token_introspection_disabled_reason": "short-lived issuer tokens",
    }
    values.update(overrides)
    return Settings(**values)


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"token_issuer": None}, "WORKSTREAM_TOKEN_ISSUER"),
        ({"token_jwks_url": "http://issuer.example.test/jwks"}, "canonical HTTPS"),
        ({"token_algorithms": "HS256"}, "unsupported algorithm"),
        ({"token_algorithms": "RS256,ES256"}, "mix key families"),
        ({"token_introspection_mode": None}, "INTROSPECTION_MODE"),
        ({"token_introspection_disabled_reason": None}, "DISABLED_REASON"),
        ({"token_header_max_bytes": 8_192, "token_max_bytes": 4_096}, "header limit"),
        ({"token_issuer": "https://auth.flow.local"}, "placeholder issuer"),
        ({"required_human_scope": "  "}, "HUMAN_SCOPE"),
        ({"required_service_scope": "two scopes"}, "SERVICE_SCOPE"),
    ],
)
def test_flow_verifier_rejects_incomplete_or_unsafe_configuration(
    overrides: dict,
    message: str,
) -> None:
    with pytest.raises(RuntimeError, match=message):
        FlowAuthVerifier(_flow_settings(**overrides))


def test_required_introspection_requires_endpoint_credentials() -> None:
    with pytest.raises(RuntimeError, match="INTROSPECTION_URL"):
        FlowAuthVerifier(
            _flow_settings(
                token_introspection_mode="required",
                token_introspection_disabled_reason=None,
            )
        )


@pytest.mark.parametrize(
    "field_name",
    ["token_introspection_client_id", "token_introspection_client_secret"],
)
def test_required_introspection_rejects_whitespace_credentials(field_name: str) -> None:
    values = {
        "token_introspection_mode": "required",
        "token_introspection_disabled_reason": None,
        "token_introspection_url": "https://introspection.example.test/introspect",
        "token_introspection_client_id": "client-id",
        "token_introspection_client_secret": "client-secret",
    }
    values[field_name] = "  "
    with pytest.raises(RuntimeError, match=field_name.removeprefix("token_").upper()):
        FlowAuthVerifier(_flow_settings(**values))


def test_numeric_security_bounds_are_validated() -> None:
    with pytest.raises(ValidationError):
        Settings(token_jwks_max_keys=101)


def test_production_flow_verifier_is_process_cached(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WORKSTREAM_AUTH_PROVIDER", "flow")
    monkeypatch.setenv("WORKSTREAM_ENVIRONMENT", "production")
    monkeypatch.setenv("WORKSTREAM_TOKEN_ISSUER", "https://issuer.example.test")
    monkeypatch.setenv("WORKSTREAM_TOKEN_JWKS_URL", "https://issuer.example.test/jwks")
    monkeypatch.setenv("WORKSTREAM_TOKEN_ALGORITHMS", "RS256")
    monkeypatch.setenv("WORKSTREAM_TOKEN_INTROSPECTION_MODE", "disabled")
    monkeypatch.setenv(
        "WORKSTREAM_TOKEN_INTROSPECTION_DISABLED_REASON",
        "short-lived issuer tokens",
    )
    get_settings.cache_clear()
    clear_auth_verifier_cache()
    try:
        assert get_auth_verifier() is get_auth_verifier()
    finally:
        get_settings.cache_clear()
        clear_auth_verifier_cache()


async def test_invalid_production_auth_configuration_rejects_application_startup() -> None:
    app = create_app(Settings(environment="production", auth_provider="flow"))

    with pytest.raises(RuntimeError, match="WORKSTREAM_TOKEN_ISSUER"):
        async with app.router.lifespan_context(app):
            pass


async def test_valid_production_auth_configuration_allows_application_startup() -> None:
    app = create_app(
        _flow_settings(
            environment="production",
            token_introspection_mode="disabled",
            token_introspection_disabled_reason="short-lived issuer tokens",
        )
    )

    retained_verifier = app.state.auth_verifier
    async with app.router.lifespan_context(app):
        assert app.state.auth_verifier is retained_verifier
        assert (
            get_application_auth_verifier(type("Request", (), {"app": app})()) is retained_verifier
        )


@pytest.mark.parametrize("environment", ["staging", "preview", "prod", "production"])
def test_settings_reject_local_artifacts_outside_development(environment: str) -> None:
    """Keep filesystem storage out of production-like deployments."""
    with pytest.raises(ValidationError, match="local artifact storage"):
        Settings(
            environment=environment,
            artifact_store_backend="local",
            artifact_local_root="/tmp/workstream-artifacts",
            artifact_scratch_root="/tmp/workstream-artifact-scratch",
        )


def test_settings_require_scratch_root_for_enabled_artifacts() -> None:
    with pytest.raises(ValidationError, match="artifact scratch root"):
        Settings(
            environment="test",
            artifact_store_backend="s3_compatible",
        )


@pytest.mark.parametrize("interval", [0, -1, 86_401])
def test_artifact_scratch_cleanup_interval_is_positive_and_bounded(interval: int) -> None:
    with pytest.raises(ValidationError):
        Settings(artifact_scratch_cleanup_interval_seconds=interval)


def test_artifact_backend_enum_is_exact_and_flow_node_is_rejected(tmp_path: Path) -> None:
    annotation = Settings.model_fields["artifact_store_backend"].annotation
    assert get_args(annotation) == ("disabled", "local", "s3_compatible")

    with pytest.raises(ValidationError):
        Settings(
            environment="test",
            artifact_store_backend="flow_node",  # type: ignore[arg-type]
            artifact_scratch_root=tmp_path / "scratch",
        )


def test_local_artifact_settings_and_factory(tmp_path: Path) -> None:
    """Construct local storage only from complete development configuration."""
    settings = Settings(
        environment="test",
        artifact_store_backend="local",
        artifact_local_root=tmp_path / "artifacts",
        artifact_scratch_root=tmp_path / "scratch",
        artifact_stream_buffer_bytes=64,
        artifact_operation_lock_timeout_seconds=17,
    )
    (tmp_path / "artifacts").mkdir(mode=0o700)
    adapter = create_artifact_store_bootstrap(settings)
    assert adapter.identity.capability_key == "artifact_store"
    assert adapter.identity.provider_key == "local"
    assert adapter._adapter._lock_timeout_seconds == 17
    adapter.close()
    incomplete = settings.model_copy(update={"artifact_local_root": None})
    with pytest.raises(UnknownExternalServiceProviderError) as disabled:
        create_artifact_store_bootstrap(Settings())
    assert disabled.value.identity is not None
    assert disabled.value.identity.provider_key == "disabled"
    with pytest.raises(ExternalServiceConfigurationError):
        create_artifact_store_bootstrap(incomplete)


def test_artifact_scratch_settings_are_bounded_and_separate(tmp_path) -> None:
    """Validate the inactive scratch boundary without activating a runtime path."""
    settings = Settings(
        artifact_scratch_root=tmp_path / "scratch",
        artifact_scratch_aggregate_reserved_bytes=2 * 512 * 1024 * 1024,
        artifact_scratch_maximum_files=4,
        artifact_scratch_maximum_concurrency=2,
        artifact_scratch_minimum_free_bytes=128 * 1024 * 1024,
        artifact_scratch_reservation_ttl_seconds=2400,
        artifact_preparation_total_deadline_seconds=1800,
        artifact_scratch_cleanup_margin_seconds=300,
    )
    assert settings.artifact_scratch_root == tmp_path / "scratch"
    assert settings.artifact_scratch_maximum_concurrency == 2

    with pytest.raises(ValidationError, match="concurrency cannot exceed"):
        Settings(
            artifact_scratch_maximum_files=1,
            artifact_scratch_maximum_concurrency=2,
        )
    with pytest.raises(ValidationError, match="deadline must expire before"):
        Settings(
            artifact_scratch_reservation_ttl_seconds=600,
            artifact_preparation_total_deadline_seconds=500,
            artifact_scratch_cleanup_margin_seconds=100,
        )
    with pytest.raises(ValidationError, match="roots must be separate"):
        Settings(
            artifact_local_root=tmp_path / "artifacts",
            artifact_scratch_root=tmp_path / "artifacts" / "scratch",
        )


def test_s3_compatible_factory_fails_typed_until_adapter_chunk(tmp_path: Path) -> None:
    """Keep valid future S3 configuration unavailable until its owned chunk."""
    settings = Settings(
        environment="test",
        artifact_store_backend="s3_compatible",
        artifact_scratch_root=tmp_path / "scratch",
    )
    with pytest.raises(UnknownExternalServiceProviderError) as caught:
        create_artifact_store_bootstrap(settings)

    assert caught.value.identity is not None
    assert caught.value.identity.provider_key == "s3_compatible"
