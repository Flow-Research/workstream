from __future__ import annotations

import base64
import importlib.metadata
import json
import tomllib
from collections.abc import Mapping
from pathlib import Path
from typing import get_args

import pytest
from pydantic import ValidationError
from pydantic_settings import BaseSettings

from app.adapters.artifacts import create_artifact_store_bootstrap
from app.adapters.artifacts.s3_compatible import create_minio_artifact_store_bootstrap
from app.adapters.auth.flow import FlowAuthVerifier
from app.api.deps.auth import get_application_auth_verifier
from app.core.auth import clear_auth_verifier_cache, get_auth_verifier
from app.core.config import Settings, get_settings
from app.core.s3_validation import (
    canonical_minio_endpoint,
    is_canonical_s3_region,
    is_canonical_s3_prefix,
    validate_s3_namespace_descriptor,
)
from app.interfaces.artifacts import (
    ArtifactConfigurationError,
    ArtifactProviderLiveProofRequiredError,
)
from app.interfaces.external_services import (
    ExternalServiceConfigurationError,
    UnknownExternalServiceProviderError,
)
from app.main import create_app
from tests.assertion_helpers import assert_secret_not_retained
from tests.artifact_store_helpers import artifact_admission_limit_settings


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
    assert_secret_not_retained(
        caught.value,
        encoded,
        traceback_module_prefixes=("app.",),
    )


def test_environment_rate_limit_secret_is_absent_from_unrelated_structured_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    encoded = base64.b64encode(bytes(range(32))).decode("ascii")
    monkeypatch.setenv("WORKSTREAM_API_RATE_LIMIT_KEY_SECRET", encoded)

    with pytest.raises(ValidationError) as caught:
        Settings(artifact_store_backend="flow_node")

    assert encoded not in repr(caught.value.errors())
    assert encoded not in caught.value.json()
    assert_secret_not_retained(
        caught.value,
        encoded,
        traceback_module_prefixes=("app.",),
    )


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
    assert_secret_not_retained(
        caught.value,
        encoded,
        traceback_module_prefixes=("app.",),
    )


def test_model_validate_rejects_rate_limit_secret_without_structured_echo() -> None:
    invalid = "not-a-canonical-secret"

    with pytest.raises(ValueError, match="^invalid API rate limit key secret$") as caught:
        Settings.model_validate({"api_rate_limit_key_secret": invalid})

    assert not isinstance(caught.value, ValidationError)
    assert invalid not in f"{caught.value!s} {caught.value!r}"
    assert_secret_not_retained(
        caught.value,
        invalid,
        traceback_module_prefixes=("app.",),
    )


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
    assert_secret_not_retained(
        caught.value,
        encoded,
        traceback_module_prefixes=("app.",),
    )


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
        observed["input"] = dict(obj) if isinstance(obj, Mapping) else obj
        raise PydanticBoundaryReached

    monkeypatch.setattr(BaseSettings, base_method_name, classmethod(capture_input))
    payload = {"api_rate_limit_key_secret": encoded}
    method = getattr(Settings, method_name)

    with pytest.raises(PydanticBoundaryReached):
        method(json.dumps(payload) if method_name.endswith("json") else payload)

    assert isinstance(observed["input"], Mapping)
    assert observed["input"]["api_rate_limit_key_secret"] is None
    assert_secret_not_retained(observed, encoded)


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
    assert_secret_not_retained(
        caught.value,
        invalid,
        traceback_module_prefixes=("app.",),
    )


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
    assert_secret_not_retained(
        caught.value,
        encoded,
        traceback_module_prefixes=("app.",),
    )


@pytest.mark.parametrize(
    "field_name",
    ["api_rate_limit_key_secret", "artifact_s3_secret_access_key"],
)
def test_model_validate_json_rejects_malformed_document_without_echo(
    field_name: str,
) -> None:
    invalid = "not-a-canonical-secret"
    payload = f'{{"{field_name}":"{invalid}"'

    with pytest.raises(ValueError, match="^invalid settings JSON$") as caught:
        Settings.model_validate_json(payload)

    assert not isinstance(caught.value, ValidationError)
    assert invalid not in f"{caught.value!s} {caught.value!r}"
    assert caught.value.__cause__ is None
    assert caught.value.__context__ is None
    assert_secret_not_retained(
        caught.value,
        invalid,
        traceback_module_prefixes=("app.",),
    )


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
        assert_secret_not_retained(
            caught.value,
            value,
            traceback_module_prefixes=("app.",),
        )


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


def _minio_setting_values(tmp_path: Path, **overrides: object) -> dict[str, object]:
    values: dict[str, object] = {
        **artifact_admission_limit_settings(),
        "environment": "test",
        "artifact_store_backend": "s3_compatible",
        "artifact_scratch_root": tmp_path / "scratch",
        "artifact_s3_provider_profile": "minio",
        "artifact_s3_region": "us-east-1",
        "artifact_s3_endpoint_url": "http://127.0.0.1:9000",
        "artifact_s3_bucket": "workstream-artifacts-test",
        "artifact_s3_private_prefix": "workstream/artifacts",
        "artifact_s3_addressing_style": "path",
        "artifact_s3_credential_mode": "local_static",
        "artifact_s3_access_key_id": "minio-access-key",
        "artifact_s3_secret_access_key": "minio-secret-key",
    }
    values.update(overrides)
    return values


def _minio_settings(tmp_path: Path, **overrides: object) -> Settings:
    return Settings(**_minio_setting_values(tmp_path, **overrides))


def _aws_settings(tmp_path: Path, **overrides: object) -> Settings:
    values: dict[str, object] = {
        **artifact_admission_limit_settings(),
        "environment": "production",
        "artifact_store_backend": "s3_compatible",
        "artifact_scratch_root": tmp_path / "scratch",
        "artifact_s3_provider_profile": "aws_s3",
        "artifact_s3_region": "us-east-1",
        "artifact_s3_bucket": "workstream-artifacts-prod",
        "artifact_s3_private_prefix": "workstream/artifacts",
        "artifact_s3_addressing_style": "virtual",
        "artifact_s3_credential_mode": "aws_workload_identity",
        "artifact_s3_aws_workload_identity_method": "container-role",
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
            **artifact_admission_limit_settings(),
            environment=environment,
            artifact_store_backend="local",
            artifact_local_root="/tmp/workstream-artifacts",
            artifact_scratch_root="/tmp/workstream-artifact-scratch",
        )


def test_settings_require_scratch_root_for_enabled_artifacts() -> None:
    with pytest.raises(ValidationError, match="artifact scratch root"):
        Settings(
            **artifact_admission_limit_settings(),
            environment="test",
            artifact_store_backend="s3_compatible",
        )


def test_settings_require_every_durable_byte_admission_limit(tmp_path: Path) -> None:
    """Enabled stores must never inherit an implicit capacity policy."""
    common = {
        "environment": "test",
        "artifact_store_backend": "local",
        "artifact_local_root": tmp_path / "artifacts",
        "artifact_scratch_root": tmp_path / "scratch",
    }
    with pytest.raises(
        ValidationError,
        match="requires all durable-byte admission limits",
    ):
        Settings(**common)

    partial = artifact_admission_limit_settings()
    partial.pop("artifact_admission_task_maximum_bytes")
    with pytest.raises(
        ValidationError,
        match="requires all durable-byte admission limits",
    ):
        Settings(**common, **partial)

    settings = Settings(**common, **artifact_admission_limit_settings())
    assert settings.artifact_admission_task_maximum_bytes == 1024


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
        **artifact_admission_limit_settings(),
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


def test_minio_settings_and_factory_construct_closed_namespace(tmp_path: Path) -> None:
    """MinIO is the active S3-compatible runtime profile for local and CI proof."""
    settings = _minio_settings(tmp_path)

    bootstrap = create_artifact_store_bootstrap(settings)

    try:
        assert bootstrap.identity.capability_key == "artifact_store"
        assert bootstrap.identity.provider_key == "s3_compatible"
        assert bootstrap.namespace_identity.provider_profile == "minio-v1"
        assert bootstrap.namespace_identity.descriptor_items == (
            ("addressing_style", "path"),
            ("bucket", "workstream-artifacts-test"),
            ("endpoint_identity", bootstrap.namespace_identity.as_dict()["endpoint_identity"]),
            ("private_prefix", "workstream/artifacts"),
            ("region", "us-east-1"),
        )
        endpoint_identity = bootstrap.namespace_identity.as_dict()["endpoint_identity"]
        assert endpoint_identity.startswith("sha256:")
        assert "127.0.0.1" not in endpoint_identity
        assert "minio-secret-key" not in repr(bootstrap.namespace_identity)
    finally:
        bootstrap.close()


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"artifact_s3_provider_profile": None}, "requires a provider profile"),
        ({"artifact_s3_region": "US-east-1"}, "requires a canonical region"),
        ({"artifact_s3_region": "us-east-1-"}, "requires a canonical region"),
        ({"artifact_s3_region": "1-east-1"}, "requires a canonical region"),
        ({"artifact_s3_region": "a-east-1"}, "requires a canonical region"),
        ({"artifact_s3_bucket": "192.168.0.1"}, "requires a canonical bucket"),
        ({"artifact_s3_bucket": "bucket..name"}, "requires a canonical bucket"),
        ({"artifact_s3_bucket": "bucket.-name"}, "requires a canonical bucket"),
        ({"artifact_s3_bucket": "bucket-.name"}, "requires a canonical bucket"),
        ({"artifact_s3_bucket": "xn--bucket"}, "requires a canonical bucket"),
        ({"artifact_s3_bucket": "sthree-bucket"}, "requires a canonical bucket"),
        ({"artifact_s3_bucket": "amzn-s3-demo-bucket"}, "requires a canonical bucket"),
        ({"artifact_s3_bucket": "bucket-s3alias"}, "requires a canonical bucket"),
        ({"artifact_s3_bucket": "bucket--ol-s3"}, "requires a canonical bucket"),
        ({"artifact_s3_bucket": "bucket.mrap"}, "requires a canonical bucket"),
        ({"artifact_s3_bucket": "bucket--x-s3"}, "requires a canonical bucket"),
        ({"artifact_s3_bucket": "bucket--table-s3"}, "requires a canonical bucket"),
        ({"artifact_s3_bucket": "bucket-an"}, "requires a canonical bucket"),
        ({"artifact_s3_private_prefix": "/bad"}, "private prefix is invalid"),
        ({"artifact_maximum_bytes": 512 * 1024 * 1024 + 1}, "maximum exceeds"),
        ({"environment": "production"}, "MinIO artifact storage is restricted"),
        ({"artifact_s3_credential_mode": "aws_workload_identity"}, "local static"),
        (
            {"artifact_s3_aws_workload_identity_method": "iam-role"},
            "cannot select AWS workload identity",
        ),
        ({"artifact_s3_endpoint_url": None}, "requires an endpoint"),
        ({"artifact_s3_endpoint_url": "https://user:pass@minio.test"}, "endpoint is invalid"),
        ({"artifact_s3_endpoint_url": "http://minio.test/path"}, "endpoint is invalid"),
    ],
)
def test_minio_settings_fail_closed(
    tmp_path: Path,
    overrides: dict[str, object],
    message: str,
) -> None:
    with pytest.raises((ValidationError, ValueError), match=message):
        _minio_settings(tmp_path, **overrides)


def test_mutated_minio_settings_cannot_retain_credentials_in_constructor_error(
    tmp_path: Path,
) -> None:
    access_key = "minio-mutated-access-key"
    secret_key = "minio-mutated-secret-key"
    settings = _minio_settings(
        tmp_path,
        artifact_s3_access_key_id=access_key,
        artifact_s3_secret_access_key=secret_key,
    )
    settings.artifact_s3_bucket = "bucket.-invalid"

    with pytest.raises(ArtifactConfigurationError) as caught:
        create_minio_artifact_store_bootstrap(settings)

    assert caught.value.__cause__ is None
    assert caught.value.__context__ is None
    assert_secret_not_retained(
        caught.value,
        access_key,
        traceback_module_prefixes=("app.adapters.artifacts.s3_compatible",),
    )
    assert_secret_not_retained(
        caught.value,
        secret_key,
        traceback_module_prefixes=("app.adapters.artifacts.s3_compatible",),
    )

    with pytest.raises(ExternalServiceConfigurationError) as public_error:
        create_artifact_store_bootstrap(settings)
    assert_secret_not_retained(
        public_error.value,
        access_key,
        traceback_module_prefixes=(
            "app.adapters.artifacts.s3_compatible",
            "app.interfaces.external_services",
        ),
    )
    assert_secret_not_retained(
        public_error.value,
        secret_key,
        traceback_module_prefixes=(
            "app.adapters.artifacts.s3_compatible",
            "app.interfaces.external_services",
        ),
    )


@pytest.mark.parametrize(
    ("removed", "message"),
    [
        ("artifact_s3_access_key_id", "complete static credentials"),
        ("artifact_s3_secret_access_key", "complete static credentials"),
    ],
)
def test_minio_static_credentials_are_required(
    tmp_path: Path,
    removed: str,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        _minio_settings(tmp_path, **{removed: None})


def test_minio_secret_values_are_absent_from_repr_and_validation_errors(
    tmp_path: Path,
) -> None:
    secret = "minio-secret-value-that-must-not-leak"
    settings = _minio_settings(tmp_path, artifact_s3_secret_access_key=secret)

    assert settings.artifact_s3_secret_access_key is not None
    assert settings.artifact_s3_secret_access_key.get_secret_value() == secret
    assert secret not in repr(settings)
    assert secret not in repr(settings.model_dump())

    with pytest.raises(ValidationError) as caught:
        _minio_settings(
            tmp_path,
            artifact_s3_secret_access_key=secret,
            artifact_s3_region="US-east-1",
        )

    assert secret not in repr(caught.value.errors())
    assert secret not in caught.value.json()
    assert_secret_not_retained(
        caught.value,
        secret,
        traceback_module_prefixes=("app.",),
    )


@pytest.mark.parametrize(
    "method_name",
    ["model_validate", "model_validate_json", "model_validate_strings"],
)
def test_valid_minio_secret_is_absent_from_unrelated_application_traceback(
    tmp_path: Path,
    method_name: str,
) -> None:
    """Later configuration errors must not retain an accepted credential."""
    secret = "valid-minio-secret-for-traceback"
    payload = _minio_setting_values(
        tmp_path,
        artifact_scratch_root=str(tmp_path / "scratch"),
        artifact_s3_secret_access_key=secret,
        artifact_s3_region="US-east-1",
    )
    method = getattr(Settings, method_name)

    with pytest.raises(ValueError) as caught:
        method(json.dumps(payload) if method_name.endswith("json") else payload)

    assert_secret_not_retained(
        caught.value,
        secret,
        traceback_module_prefixes=("app.",),
    )


@pytest.mark.parametrize(
    "method_name",
    ["constructor", "model_validate", "model_validate_json", "model_validate_strings"],
)
def test_invalid_minio_secret_is_absent_from_application_traceback(
    tmp_path: Path,
    method_name: str,
) -> None:
    """Rejected credentials must not remain in Workstream traceback locals."""
    secret = "invalid-minio-secret\n"
    payload = _minio_setting_values(
        tmp_path,
        artifact_scratch_root=str(tmp_path / "scratch"),
        artifact_s3_secret_access_key=secret,
    )

    with pytest.raises(ValueError, match="invalid artifact storage secret") as caught:
        if method_name == "constructor":
            Settings(**payload)
        elif method_name == "model_validate_json":
            Settings.model_validate_json(json.dumps(payload))
        else:
            getattr(Settings, method_name)(payload)

    assert_secret_not_retained(
        caught.value,
        secret,
        traceback_module_prefixes=("app.",),
    )


@pytest.mark.parametrize(
    ("method_name", "delegated_method", "error_type"),
    [
        ("constructor", "__init__", RuntimeError),
        ("model_validate", "model_validate", RuntimeError),
        ("model_validate_json", "model_validate", TypeError),
        ("model_validate_strings", "model_validate_strings", TypeError),
    ],
)
def test_unexpected_validation_errors_do_not_retain_minio_secrets(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    method_name: str,
    delegated_method: str,
    error_type: type[Exception],
) -> None:
    """Unexpected delegated errors must still clear every credential local."""
    secret = "minio-secret-from-unexpected-validator-error"
    payload = _minio_setting_values(
        tmp_path,
        artifact_scratch_root=str(tmp_path / "scratch"),
        artifact_s3_secret_access_key=secret,
    )

    def fail_validation(*args: object, **kwargs: object) -> None:
        del args, kwargs
        raise error_type("forced validation failure")

    if delegated_method == "__init__":
        monkeypatch.setattr(BaseSettings, delegated_method, fail_validation)
    else:
        monkeypatch.setattr(
            BaseSettings,
            delegated_method,
            classmethod(fail_validation),
        )

    with pytest.raises(error_type, match="^forced validation failure$") as caught:
        if method_name == "constructor":
            Settings(**payload)
        elif method_name == "model_validate_json":
            Settings.model_validate_json(json.dumps(payload))
        else:
            getattr(Settings, method_name)(payload)

    assert_secret_not_retained(
        caught.value,
        secret,
        traceback_module_prefixes=("app.",),
    )


@pytest.mark.parametrize(
    ("field_name", "field_value"),
    [
        ("artifact_s3_access_key_id", "nested-json-secret"),
        ("artifact_s3_secret_access_key", "nested-json-secret"),
        ("artifact_s3_session_token", "nested-json-secret"),
        (
            "artifact_s3_endpoint_url",
            "http://user:nested-json-secret@localhost:9000",
        ),
    ],
)
def test_invalid_json_shapes_do_not_retain_minio_secrets(
    field_name: str,
    field_value: str,
) -> None:
    """Rejected non-object JSON must not survive in Workstream error frames."""
    secret = "nested-json-secret"
    payload = json.dumps([{field_name: field_value}])

    with pytest.raises(ValueError, match="^invalid settings JSON$") as caught:
        Settings.model_validate_json(payload)

    assert secret not in f"{caught.value!s} {caught.value!r}"
    assert_secret_not_retained(
        caught.value,
        secret,
        traceback_module_prefixes=("app.",),
    )


def test_partial_s3_secret_extraction_cleans_unexpected_dotenv_errors(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """A later source error must not retain an already-extracted credential."""
    monkeypatch.delenv("WORKSTREAM_ARTIFACT_S3_SECRET_ACCESS_KEY", raising=False)
    rate_secret = base64.b64encode(bytes(range(32))).decode("ascii")
    access_key = "partially-extracted-minio-access-key"
    payload = _minio_setting_values(
        tmp_path,
        api_rate_limit_key_secret=rate_secret,
        artifact_s3_access_key_id=access_key,
        _env_file=object(),
    )
    payload.pop("artifact_s3_secret_access_key")

    with pytest.raises(TypeError) as caught:
        Settings(**payload)

    assert_secret_not_retained(
        caught.value,
        access_key,
        traceback_module_prefixes=("app.core.config",),
    )


@pytest.mark.parametrize(
    "method_name",
    ["model_validate", "model_validate_json", "model_validate_strings"],
)
def test_alternate_validation_loads_minio_secrets_without_retaining_them(
    tmp_path: Path,
    method_name: str,
) -> None:
    secret = "alternate-minio-secret-value"
    payload = _minio_setting_values(
        tmp_path,
        artifact_scratch_root=str(tmp_path / "scratch"),
        artifact_s3_secret_access_key=secret,
    )
    method = getattr(Settings, method_name)

    settings = method(json.dumps(payload) if method_name.endswith("json") else payload)

    assert settings.artifact_s3_secret_access_key is not None
    assert settings.artifact_s3_secret_access_key.get_secret_value() == secret
    assert secret not in repr(settings)
    assert secret not in repr(settings.model_dump())


def test_minio_secret_values_from_env_and_dotenv_are_absent_from_errors(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    env_secret = "env-minio-secret-value"
    dotenv_secret = "dotenv-minio-secret-value"
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "WORKSTREAM_ARTIFACT_S3_ACCESS_KEY_ID=dotenv-access",
                f"WORKSTREAM_ARTIFACT_S3_SECRET_ACCESS_KEY={dotenv_secret}",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("WORKSTREAM_ARTIFACT_S3_ACCESS_KEY_ID", "env-access")
    monkeypatch.setenv("WORKSTREAM_ARTIFACT_S3_SECRET_ACCESS_KEY", env_secret)

    with pytest.raises(ValidationError) as env_error:
        Settings(
            **artifact_admission_limit_settings(),
            environment="test",
            artifact_store_backend="s3_compatible",
            artifact_scratch_root=tmp_path / "scratch",
            artifact_s3_provider_profile="minio",
            artifact_s3_region="US-east-1",
            artifact_s3_endpoint_url="http://127.0.0.1:9000",
            artifact_s3_bucket="workstream-artifacts-test",
            artifact_s3_credential_mode="local_static",
            _env_file=env_file,
        )
    assert env_secret not in repr(env_error.value.errors())
    assert_secret_not_retained(env_error.value, env_secret)

    monkeypatch.delenv("WORKSTREAM_ARTIFACT_S3_ACCESS_KEY_ID")
    monkeypatch.delenv("WORKSTREAM_ARTIFACT_S3_SECRET_ACCESS_KEY")
    with pytest.raises(ValidationError) as dotenv_error:
        Settings(
            **artifact_admission_limit_settings(),
            environment="test",
            artifact_store_backend="s3_compatible",
            artifact_scratch_root=tmp_path / "scratch",
            artifact_s3_provider_profile="minio",
            artifact_s3_region="US-east-1",
            artifact_s3_endpoint_url="http://127.0.0.1:9000",
            artifact_s3_bucket="workstream-artifacts-test",
            artifact_s3_credential_mode="local_static",
            _env_file=env_file,
        )
    assert dotenv_secret not in repr(dotenv_error.value.errors())
    assert_secret_not_retained(dotenv_error.value, dotenv_secret)


def test_minio_endpoint_is_normalized_before_namespace_identity(tmp_path: Path) -> None:
    """Equivalent MinIO origins must produce one endpoint and namespace identity."""
    common = {
        **artifact_admission_limit_settings(),
        "environment": "test",
        "artifact_store_backend": "s3_compatible",
        "artifact_scratch_root": tmp_path / "scratch",
        "artifact_s3_provider_profile": "minio",
        "artifact_s3_region": "us-east-1",
        "artifact_s3_bucket": "workstream-artifacts-test",
        "artifact_s3_credential_mode": "local_static",
        "artifact_s3_access_key_id": "local-access",
        "artifact_s3_secret_access_key": "local-secret",
    }
    canonical = Settings(**common, artifact_s3_endpoint_url="http://localhost")
    equivalent = Settings(**common, artifact_s3_endpoint_url="HTTP://LOCALHOST:80/")

    assert canonical.artifact_s3_endpoint_url == "http://localhost"
    assert equivalent.artifact_s3_endpoint_url == "http://localhost"
    assert (
        create_artifact_store_bootstrap(canonical).namespace_identity
        == create_artifact_store_bootstrap(equivalent).namespace_identity
    )


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"artifact_s3_endpoint_url": "https://s3.us-east-1.amazonaws.com"}, "endpoint"),
        ({"artifact_s3_credential_mode": "local_static"}, "workload identity"),
        ({"artifact_s3_aws_workload_identity_method": None}, "one workload identity"),
        (
            {
                "artifact_s3_access_key_id": "static-access",
                "artifact_s3_secret_access_key": "static-secret",
            },
            "rejects static credentials",
        ),
    ],
)
def test_aws_s3_settings_fail_closed(
    tmp_path: Path,
    overrides: dict[str, object],
    message: str,
) -> None:
    with pytest.raises((ValidationError, ValueError), match=message):
        _aws_settings(tmp_path, **overrides)


def test_aws_factory_fails_with_live_proof_before_constructing_provider(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from app.adapters import artifacts as artifacts_module
    from app.adapters.artifacts import s3_compatible

    settings = _aws_settings(tmp_path)
    events: list[str] = []

    class FactoryMustNotConstruct:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            events.append("factory")
            raise AssertionError("factory constructed before AWS live proof failure")

    def session_must_not_construct(*_args: object, **_kwargs: object) -> object:
        events.append("resolver")
        raise AssertionError("credential resolver constructed before live proof failure")

    def credentials_must_not_be_probed(*_args: object, **_kwargs: object) -> None:
        events.append("credential-probe")
        raise AssertionError("credential sources probed before live proof failure")

    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("AWS_CONTAINER_CREDENTIALS_RELATIVE_URI", "/v2/credentials/runtime")
    monkeypatch.setattr(artifacts_module, "ExternalServiceAdapterFactory", FactoryMustNotConstruct)
    monkeypatch.setattr(s3_compatible, "AioSession", session_must_not_construct)
    monkeypatch.setattr(
        s3_compatible,
        "validate_aws_workload_identity_environment",
        credentials_must_not_be_probed,
    )

    with pytest.raises(ArtifactProviderLiveProofRequiredError) as caught:
        create_artifact_store_bootstrap(settings)

    assert caught.value.code == "artifact_provider_live_proof_required"
    assert events == []


async def test_aws_lifespan_fails_before_namespace_claim_and_provider_io(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    import app.main as main_module

    settings = _aws_settings(tmp_path, environment="test")
    events: list[str] = []

    async def namespace_must_not_run(*_args: object, **_kwargs: object) -> object:
        events.append("namespace")
        raise AssertionError("namespace claim ran before AWS live proof failure")

    async def cleanup_must_not_run(*_args: object, **_kwargs: object) -> object:
        events.append("cleanup")
        raise AssertionError("provider cleanup ran before AWS live proof failure")

    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("AWS_CONTAINER_CREDENTIALS_RELATIVE_URI", "/v2/credentials/runtime")
    monkeypatch.setattr(
        main_module,
        "_validate_artifact_storage_namespace_at_startup",
        namespace_must_not_run,
    )
    monkeypatch.setattr(main_module, "cleanup_stale_artifact_scratch", cleanup_must_not_run)
    app = create_app(settings)

    with pytest.raises(ArtifactProviderLiveProofRequiredError) as caught:
        async with app.router.lifespan_context(app):
            pass

    assert caught.value.code == "artifact_provider_live_proof_required"
    assert events == []


def test_s3_dependency_manifest_and_installed_versions_are_exact() -> None:
    manifest = tomllib.loads((Path(__file__).parents[1] / "pyproject.toml").read_text())

    assert "aiobotocore==3.7.0" in manifest["project"]["dependencies"]
    assert "botocore==1.43.0" in manifest["project"]["dependencies"]
    assert importlib.metadata.version("aiobotocore") == "3.7.0"
    assert importlib.metadata.version("botocore") == "1.43.0"


@pytest.mark.parametrize("value", [None, "", "x" * 513])
def test_s3_prefix_validation_rejects_noncanonical_outer_bounds(value: object) -> None:
    assert is_canonical_s3_prefix(value) is False


def test_minio_endpoint_canonicalization_handles_ipv6_and_invalid_ports() -> None:
    assert canonical_minio_endpoint("HTTP://[::1]:9000/") == "http://[::1]:9000"
    assert (
        canonical_minio_endpoint("http://[0:0:0:0:0:0:0:1]:9000")
        == "http://[::1]:9000"
    )
    with pytest.raises(ValueError, match="endpoint is invalid"):
        canonical_minio_endpoint("http://localhost:not-a-port")


@pytest.mark.parametrize(
    "region",
    ["us-east-1", "us-gov-west-1", "eusc-de-east-1"],
)
def test_s3_region_validation_accepts_canonical_region_shapes(region: str) -> None:
    assert is_canonical_s3_region(region) is True


@pytest.mark.parametrize(
    "endpoint",
    [
        "http://user:endpoint-secret@localhost:9000",
        "http://localhost:endpoint-secret",
    ],
)
def test_invalid_minio_endpoint_secrets_do_not_survive_errors(
    tmp_path: Path,
    endpoint: str,
) -> None:
    secret = "endpoint-secret"

    with pytest.raises(ValueError) as endpoint_error:
        canonical_minio_endpoint(endpoint)
    assert_secret_not_retained(
        endpoint_error.value,
        secret,
        traceback_module_prefixes=("app.",),
    )

    payload = _minio_setting_values(
        tmp_path,
        artifact_scratch_root=str(tmp_path / "scratch"),
        artifact_s3_endpoint_url=endpoint,
    )
    for method_name in (
        "constructor",
        "model_validate",
        "model_validate_json",
        "model_validate_strings",
    ):
        with pytest.raises((ValidationError, ValueError)) as settings_error:
            if method_name == "constructor":
                Settings(**payload)
            elif method_name == "model_validate_json":
                Settings.model_validate_json(json.dumps(payload))
            else:
                getattr(Settings, method_name)(payload)
        assert_secret_not_retained(
            settings_error.value,
            secret,
            traceback_module_prefixes=("app.",),
        )


def test_invalid_minio_endpoint_secrets_from_env_and_dotenv_do_not_survive_errors(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    secret = "endpoint-source-secret"
    endpoint = f"http://user:{secret}@localhost:9000"
    payload = _minio_setting_values(tmp_path)
    payload.pop("artifact_s3_endpoint_url")
    monkeypatch.setenv("WORKSTREAM_ARTIFACT_S3_ENDPOINT_URL", endpoint)

    with pytest.raises(ValueError) as env_error:
        Settings(**payload)
    assert_secret_not_retained(
        env_error.value,
        secret,
        traceback_module_prefixes=("app.",),
    )

    monkeypatch.delenv("WORKSTREAM_ARTIFACT_S3_ENDPOINT_URL")
    env_file = tmp_path / ".env"
    env_file.write_text(
        f"WORKSTREAM_ARTIFACT_S3_ENDPOINT_URL={endpoint}\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError) as dotenv_error:
        Settings(**payload, _env_file=env_file)
    assert_secret_not_retained(
        dotenv_error.value,
        secret,
        traceback_module_prefixes=("app.",),
    )


@pytest.mark.parametrize(
    ("profile", "changes", "message"),
    [
        ("minio-v1", {"addressing_style": "auto"}, "addressing style"),
        ("minio-v1", {"region": "US-east-1"}, "region"),
        ("minio-v1", {"endpoint_identity": "sha256:bad"}, "endpoint identity"),
        (
            "aws-s3-v1",
            {"endpoint_identity": "sha256:" + "1" * 64},
            "endpoint identity is forbidden",
        ),
        ("unsupported-v1", {}, "provider profile"),
    ],
)
def test_s3_namespace_value_validation_fails_closed(
    profile: str,
    changes: dict[str, str],
    message: str,
) -> None:
    descriptor = {
        "addressing_style": "path",
        "bucket": "workstream-artifacts",
        "endpoint_identity": "sha256:" + "1" * 64,
        "private_prefix": "workstream/artifacts",
        "region": "us-east-1",
    }
    if profile == "aws-s3-v1":
        descriptor.pop("endpoint_identity")
    descriptor.update(changes)

    with pytest.raises(ValueError, match=message):
        validate_s3_namespace_descriptor(profile, descriptor)
