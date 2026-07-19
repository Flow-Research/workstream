from __future__ import annotations

import datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from aiobotocore.credentials import (
    AioAssumeRoleWithWebIdentityProvider,
)
from botocore.exceptions import MetadataRetrievalError, ReadTimeoutError

from app.adapters.artifacts import s3_compatible
from app.core.config import Settings
from tests.artifact_store_helpers import artifact_admission_limit_settings
from app.interfaces.artifacts import ArtifactConfigurationError
from tests.assertion_helpers import assert_secret_not_retained


def _aws_settings(tmp_path: Path, method: str = "container-role") -> Settings:
    return Settings(
        **artifact_admission_limit_settings(),
        environment="production",
        artifact_store_backend="s3_compatible",
        artifact_scratch_root=tmp_path / "scratch",
        artifact_s3_provider_profile="aws_s3",
        artifact_s3_region="us-east-1",
        artifact_s3_bucket="workstream-artifacts-prod",
        artifact_s3_private_prefix="workstream/artifacts",
        artifact_s3_addressing_style="virtual",
        artifact_s3_credential_mode="aws_workload_identity",
        artifact_s3_aws_workload_identity_method=method,  # type: ignore[arg-type]
    )


def _container_environment(tmp_path: Path, **overrides: str) -> dict[str, str]:
    environment = {
        "HOME": str(tmp_path),
        "AWS_CONTAINER_CREDENTIALS_RELATIVE_URI": "/v2/credentials/workstream-runtime",
    }
    environment.update(overrides)
    return environment


def _web_identity_environment(tmp_path: Path, **overrides: str) -> dict[str, str]:
    token = tmp_path / "web-identity-token"
    token.write_text("token", encoding="utf-8")
    environment = {
        "HOME": str(tmp_path),
        "AWS_ROLE_ARN": "arn:aws:iam::123456789012:role/workstream-runtime",
        "AWS_ROLE_SESSION_NAME": "workstream-artifact-runtime",
        "AWS_WEB_IDENTITY_TOKEN_FILE": str(token),
    }
    environment.update(overrides)
    return environment


def _iam_environment(tmp_path: Path, **overrides: str) -> dict[str, str]:
    environment = {
        "HOME": str(tmp_path),
        "AWS_EC2_METADATA_V1_DISABLED": "true",
    }
    environment.update(overrides)
    return environment


def _assert_rejects_before_session_construction(
    monkeypatch: pytest.MonkeyPatch,
    settings: Settings,
    environment: dict[str, str],
    match: str,
) -> None:
    events: list[str] = []

    def session_must_not_construct(*_args: object, **_kwargs: object) -> object:
        events.append("session")
        raise AssertionError("SDK session constructed before isolation rejection")

    monkeypatch.setattr(s3_compatible, "AioSession", session_must_not_construct)

    with pytest.raises(ArtifactConfigurationError, match=match):
        s3_compatible.create_isolated_aws_workload_identity_session(
            settings,
            environ=environment,
        )

    assert events == []


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("AWS_ACCESS_KEY", "legacy-access"),
        ("AWS_ACCESS_KEY_ID", "explicit-access"),
        ("AWS_SECRET_ACCESS_KEY", "explicit-secret"),
        ("AWS_SESSION_TOKEN", "explicit-session-token"),
        ("AWS_SECRET_KEY", "legacy-secret"),
        ("AWS_SECURITY_TOKEN", "legacy-security-token"),
        ("AWS_PROFILE", "prod"),
        ("AWS_DEFAULT_PROFILE", "prod"),
        ("AWS_SHARED_CREDENTIALS_FILE", "/tmp/credentials"),
        ("AWS_CONFIG_FILE", "/tmp/config"),
        ("AWS_CREDENTIAL_FILE", "/tmp/legacy-credentials"),
        ("AWS_LOGIN_CACHE_DIRECTORY", "/tmp/aws-login-cache"),
        ("BOTO_CONFIG", "/tmp/boto.cfg"),
    ],
)
def test_forbidden_ambient_aws_sources_fail_before_resolver_loading(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    name: str,
    value: str,
) -> None:
    _assert_rejects_before_session_construction(
        monkeypatch,
        _aws_settings(tmp_path, "container-role"),
        _container_environment(tmp_path, **{name: value}),
        "ambient AWS credential source is forbidden",
    )


@pytest.mark.parametrize(
    "name",
    [
        "AWS_CA_BUNDLE",
        "AWS_ENDPOINT_URL",
        "AWS_ENDPOINT_URL_STS",
        "AWS_STS_REGIONAL_ENDPOINTS",
        "AWS_USE_DUALSTACK_ENDPOINT",
        "AWS_USE_FIPS_ENDPOINT",
        "CURL_CA_BUNDLE",
        "REQUESTS_CA_BUNDLE",
        "SSL_CERT_DIR",
        "SSL_CERT_FILE",
    ],
)
def test_web_identity_rejects_ambient_network_configuration_before_session(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    name: str,
) -> None:
    _assert_rejects_before_session_construction(
        monkeypatch,
        _aws_settings(tmp_path, "assume-role-with-web-identity"),
        _web_identity_environment(tmp_path, **{name: "/tmp/poison"}),
        "ambient AWS network configuration is forbidden",
    )


@pytest.mark.parametrize("name", ["AWS_ENDPOINT_URL_S3", "AWS_ENDPOINT_URL_DYNAMODB"])
def test_service_specific_endpoint_override_fails_before_session_construction(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    name: str,
) -> None:
    _assert_rejects_before_session_construction(
        monkeypatch,
        _aws_settings(tmp_path, "container-role"),
        _container_environment(tmp_path, **{name: "http://127.0.0.1:9000"}),
        "ambient AWS network configuration is forbidden",
    )


@pytest.mark.parametrize(
    "name",
    [
        "AWS_ACCOUNT_ID_ENDPOINT_MODE",
        "AWS_DATA_PATH",
        "AWS_DEFAULTS_MODE",
        "AWS_ENDPOINT_DISCOVERY_ENABLED",
        "AWS_MAX_ATTEMPTS",
        "AWS_REGION",
        "AWS_RETRY_MODE",
        "BOTOCORE_CONFIG",
    ],
)
@pytest.mark.parametrize(
    ("method", "environment"),
    [
        ("assume-role-with-web-identity", _web_identity_environment),
        ("container-role", _container_environment),
        ("iam-role", _iam_environment),
    ],
)
def test_unapproved_sdk_environment_controls_fail_before_session_construction(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    name: str,
    method: str,
    environment: Any,
) -> None:
    _assert_rejects_before_session_construction(
        monkeypatch,
        _aws_settings(tmp_path, method),
        environment(tmp_path, **{name: "poison"}),
        "unsupported AWS SDK environment configuration is forbidden",
    )


@pytest.mark.parametrize(
    ("relative_path", "contents"),
    [
        (".aws/credentials", "[default]\naws_access_key_id = poison\n"),
        (".aws/config", "[profile prod]\ncredential_process = /bin/false\n"),
        (".aws/config", "[profile prod]\nsso_start_url = https://example.test/start\n"),
        (".boto", "[Credentials]\naws_access_key_id = poison\n"),
    ],
)
def test_default_credential_files_fail_before_resolver_loading(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    relative_path: str,
    contents: str,
) -> None:
    poison = tmp_path / relative_path
    poison.parent.mkdir(parents=True, exist_ok=True)
    poison.write_text(contents, encoding="utf-8")

    _assert_rejects_before_session_construction(
        monkeypatch,
        _aws_settings(tmp_path, "container-role"),
        _container_environment(tmp_path),
        "ambient AWS credential file is forbidden",
    )


@pytest.mark.parametrize(
    ("selected_method", "environment"),
    [
        (
            "assume-role-with-web-identity",
            lambda tmp_path: _web_identity_environment(
                tmp_path,
                AWS_CONTAINER_CREDENTIALS_RELATIVE_URI="/v2/credentials/poison",
            ),
        ),
        (
            "container-role",
            lambda tmp_path: _container_environment(
                tmp_path,
                AWS_ROLE_ARN="arn:aws:iam::123456789012:role/unselected",
                AWS_WEB_IDENTITY_TOKEN_FILE=str(tmp_path / "unselected-token"),
            ),
        ),
        (
            "iam-role",
            lambda tmp_path: _iam_environment(
                tmp_path,
                AWS_CONTAINER_CREDENTIALS_FULL_URI="http://127.0.0.1:9/credentials",
            ),
        ),
    ],
)
def test_unselected_workload_identity_sources_fail_before_resolver_loading(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    selected_method: str,
    environment: Any,
) -> None:
    _assert_rejects_before_session_construction(
        monkeypatch,
        _aws_settings(tmp_path, selected_method),
        environment(tmp_path),
        "unselected AWS workload source is configured",
    )


@pytest.mark.parametrize(
    ("method", "environment", "provider_type", "sdk_method"),
    [
        (
            "assume-role-with-web-identity",
            _web_identity_environment,
            AioAssumeRoleWithWebIdentityProvider,
            "assume-role-with-web-identity",
        ),
        (
            "container-role",
            _container_environment,
            s3_compatible._SanitizedContainerProvider,  # noqa: SLF001
            "container-role",
        ),
        (
            "iam-role",
            _iam_environment,
            s3_compatible._SanitizedInstanceMetadataProvider,  # noqa: SLF001
            "iam-role",
        ),
    ],
)
def test_isolated_session_contains_exactly_one_selected_provider(
    tmp_path: Path,
    method: str,
    environment: Any,
    provider_type: type[object],
    sdk_method: str,
) -> None:
    session = s3_compatible.create_isolated_aws_workload_identity_session(
        _aws_settings(tmp_path, method),
        environ=environment(tmp_path),
    )

    resolver = session.get_component("credential_provider")

    assert len(resolver.providers) == 1
    provider = resolver.providers[0]
    assert type(provider) is provider_type
    assert provider.METHOD == sdk_method
    if method == "assume-role-with-web-identity":
        assert provider._disable_env_vars is True
        assert provider._load_config() == {
            "profiles": {
                "workstream-isolated": {
                    "role_arn": "arn:aws:iam::123456789012:role/workstream-runtime",
                    "role_session_name": "workstream-artifact-runtime",
                    "web_identity_token_file": str(tmp_path / "web-identity-token"),
                }
            }
        }
    if method == "container-role":
        assert provider._environ == {
            "AWS_CONTAINER_CREDENTIALS_RELATIVE_URI": (
                "/v2/credentials/workstream-runtime"
            )
        }
        assert (
            provider._fetcher._session._proxy_config.proxy_url_for(
                "http://169.254.170.2/v2/credentials/workstream-runtime"
            )
            is None
        )
    if method == "iam-role":
        assert provider._role_fetcher._imds_v1_disabled is True
        assert (
            provider._role_fetcher._session._proxy_config.proxy_url_for(
                "http://169.254.169.254/latest/meta-data/"
            )
            is None
        )


@pytest.mark.parametrize(
    ("method", "environment", "message"),
    [
        (
            "assume-role-with-web-identity",
            lambda tmp_path: {"HOME": str(tmp_path), "AWS_ROLE_ARN": "arn"},
            "web identity configuration is incomplete",
        ),
        (
            "assume-role-with-web-identity",
            lambda tmp_path: {
                "HOME": str(tmp_path),
                "AWS_ROLE_ARN": "arn",
                "AWS_WEB_IDENTITY_TOKEN_FILE": "relative-token",
            },
            "web identity token path is invalid",
        ),
        (
            "container-role",
            lambda tmp_path: {"HOME": str(tmp_path)},
            "container identity location is invalid",
        ),
        (
            "container-role",
            lambda tmp_path: {
                "HOME": str(tmp_path),
                "AWS_CONTAINER_CREDENTIALS_FULL_URI": "https://credentials.example.test",
            },
            "container full credential URI is forbidden",
        ),
        (
            "container-role",
            lambda tmp_path: {
                "HOME": str(tmp_path),
                "AWS_CONTAINER_CREDENTIALS_FULL_URI": "http://127.0.0.1:9/full",
                "AWS_CONTAINER_CREDENTIALS_RELATIVE_URI": (
                    "/v2/credentials/workstream-runtime"
                ),
            },
            "container full credential URI is forbidden",
        ),
        (
            "container-role",
            lambda tmp_path: {
                "HOME": str(tmp_path),
                "AWS_CONTAINER_CREDENTIALS_RELATIVE_URI": (
                    "/v2/credentials/workstream-runtime"
                ),
                "AWS_CONTAINER_AUTHORIZATION_TOKEN": "token",
            },
            "container identity token is forbidden",
        ),
        (
            "container-role",
            lambda tmp_path: {
                "HOME": str(tmp_path),
                "AWS_CONTAINER_CREDENTIALS_RELATIVE_URI": (
                    "/v2/credentials/workstream-runtime"
                ),
                "AWS_CONTAINER_AUTHORIZATION_TOKEN_FILE": str(tmp_path / "token"),
            },
            "container identity token is forbidden",
        ),
        (
            "iam-role",
            lambda tmp_path: {
                "HOME": str(tmp_path),
                "AWS_EC2_METADATA_DISABLED": "true",
                "AWS_EC2_METADATA_V1_DISABLED": "true",
            },
            "instance identity metadata is disabled",
        ),
        (
            "iam-role",
            lambda tmp_path: {"HOME": str(tmp_path)},
            "instance identity requires IMDSv2",
        ),
        (
            "iam-role",
            lambda tmp_path: {
                "HOME": str(tmp_path),
                "AWS_EC2_METADATA_V1_DISABLED": "false",
            },
            "instance identity requires IMDSv2",
        ),
        (
            "iam-role",
            lambda tmp_path: {
                "HOME": str(tmp_path),
                "AWS_EC2_METADATA_SERVICE_ENDPOINT": (
                    "https://metadata.example.test/latest"
                ),
            },
            "custom AWS metadata endpoint is forbidden",
        ),
        (
            "iam-role",
            lambda tmp_path: {
                "HOME": str(tmp_path),
                "AWS_EC2_METADATA_SERVICE_ENDPOINT_MODE": "ipv6",
                "AWS_EC2_METADATA_V1_DISABLED": "true",
            },
            "custom AWS metadata endpoint mode is forbidden",
        ),
    ],
)
def test_selected_workload_identity_source_must_be_complete(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    method: str,
    environment: Any,
    message: str,
) -> None:
    _assert_rejects_before_session_construction(
        monkeypatch,
        _aws_settings(tmp_path, method),
        environment(tmp_path),
        message,
    )


@pytest.mark.parametrize(
    "relative_uri",
    [
        "/relative",
        "/v2/credentials/",
        "/v2/credentials/workstream/runtime",
        "https://credentials.example.test/v2/credentials/runtime",
        "/v2/credentials/" + "a" * 513,
    ],
)
def test_container_role_rejects_noncanonical_relative_uri(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    relative_uri: str,
) -> None:
    _assert_rejects_before_session_construction(
        monkeypatch,
        _aws_settings(tmp_path, "container-role"),
        _container_environment(
            tmp_path,
            AWS_CONTAINER_CREDENTIALS_RELATIVE_URI=relative_uri,
        ),
        "container identity location is invalid",
    )


def test_iam_metadata_session_ignores_ambient_proxy_environment(tmp_path: Path) -> None:
    session = s3_compatible.create_isolated_aws_workload_identity_session(
        _aws_settings(tmp_path, "iam-role"),
        environ=_iam_environment(
            tmp_path,
            HTTP_PROXY="http://127.0.0.1:9",
            HTTPS_PROXY="http://127.0.0.1:9",
            ALL_PROXY="http://127.0.0.1:9",
        ),
    )
    provider = session.get_component("credential_provider").providers[0]

    assert (
        provider._role_fetcher._session._proxy_config.proxy_url_for(
            "http://169.254.169.254/latest/meta-data/"
        )
        is None
    )


def test_container_metadata_session_ignores_ambient_proxy_environment(
    tmp_path: Path,
) -> None:
    session = s3_compatible.create_isolated_aws_workload_identity_session(
        _aws_settings(tmp_path, "container-role"),
        environ=_container_environment(
            tmp_path,
            HTTP_PROXY="http://127.0.0.1:9",
            HTTPS_PROXY="http://127.0.0.1:9",
            ALL_PROXY="http://127.0.0.1:9",
        ),
    )
    provider = session.get_component("credential_provider").providers[0]

    assert provider._environ == {
        "AWS_CONTAINER_CREDENTIALS_RELATIVE_URI": (
            "/v2/credentials/workstream-runtime"
        )
    }
    assert (
        provider._fetcher._session._proxy_config.proxy_url_for(
            "http://169.254.170.2/v2/credentials/workstream-runtime"
        )
        is None
    )


def test_web_identity_sts_client_ignores_ambient_proxy_environment(
    tmp_path: Path,
) -> None:
    session = s3_compatible.create_isolated_aws_workload_identity_session(
        _aws_settings(tmp_path, "assume-role-with-web-identity"),
        environ=_web_identity_environment(
            tmp_path,
            HTTP_PROXY="http://127.0.0.1:9",
            HTTPS_PROXY="http://127.0.0.1:9",
            ALL_PROXY="http://127.0.0.1:9",
        ),
    )
    provider = session.get_component("credential_provider").providers[0]
    observed: dict[str, object] = {}
    marker = object()

    def capture_client(service_name: str, **kwargs: object) -> object:
        observed["service_name"] = service_name
        observed.update(kwargs)
        return marker

    session.create_client = capture_client  # type: ignore[method-assign]

    created = provider._client_creator("sts", config=object())

    assert created is marker
    assert observed["service_name"] == "sts"
    assert observed["region_name"] == "us-east-1"
    assert observed["verify"] is True
    config = observed["config"]
    assert config.signature_version == s3_compatible.UNSIGNED
    assert config.proxies == {}


async def test_resolved_workload_identity_method_must_match() -> None:
    materialized: list[str] = []

    class FakeCredentials:
        def __init__(self, method: str) -> None:
            self.method = method

        async def get_frozen_credentials(self) -> object:
            materialized.append(self.method)
            return SimpleNamespace(access_key="access", secret_key="secret", token=None)

    class FakeSession:
        def __init__(self, method: str | None) -> None:
            self._method = method

        async def get_credentials(self) -> object | None:
            if self._method is None:
                return None
            return FakeCredentials(self._method)

    with pytest.raises(
        ArtifactConfigurationError,
        match="AWS workload identity method did not match",
    ):
        await s3_compatible.resolve_isolated_aws_workload_credentials(
            FakeSession("iam-role"),  # type: ignore[arg-type]
            expected_method="container-role",
        )

    with pytest.raises(
        ArtifactConfigurationError,
        match="AWS workload identity method did not match",
    ):
        await s3_compatible.resolve_isolated_aws_workload_credentials(
            FakeSession(None),  # type: ignore[arg-type]
            expected_method="container-role",
        )

    resolved = await s3_compatible.resolve_isolated_aws_workload_credentials(
        FakeSession("container-role"),  # type: ignore[arg-type]
        expected_method="container-role",
    )
    assert getattr(resolved, "method") == "container-role"
    assert materialized == ["container-role"]


async def test_workload_identity_materialization_failure_is_sanitized() -> None:
    secret = "deferred-credential-secret"

    class DeferredCredentials:
        method = "container-role"

        async def get_frozen_credentials(self) -> object:
            raise RuntimeError(f"credential refresh returned {secret}")

    class FakeSession:
        async def get_credentials(self) -> object:
            return DeferredCredentials()

    with pytest.raises(
        ArtifactConfigurationError,
        match="AWS workload identity credentials could not be resolved",
    ) as caught:
        await s3_compatible.resolve_isolated_aws_workload_credentials(
            FakeSession(),  # type: ignore[arg-type]
            expected_method="container-role",
        )

    assert caught.value.__cause__ is None
    assert caught.value.__context__ is None
    assert_secret_not_retained(
        caught.value,
        secret,
        traceback_module_prefixes=("app.adapters.artifacts.s3_compatible",),
    )


async def test_credential_resolution_failure_is_sanitized() -> None:
    secret = "provider-response-secret"

    class FakeSession:
        async def get_credentials(self) -> object:
            raise RuntimeError(f"credential endpoint returned {secret}")

    with pytest.raises(
        ArtifactConfigurationError,
        match="AWS workload identity credentials could not be resolved",
    ) as caught:
        await s3_compatible.resolve_isolated_aws_workload_credentials(
            FakeSession(),  # type: ignore[arg-type]
            expected_method="container-role",
        )

    assert caught.value.__cause__ is None
    assert caught.value.__context__ is None
    assert_secret_not_retained(
        caught.value,
        secret,
        traceback_module_prefixes=("app.adapters.artifacts.s3_compatible",),
    )


async def test_container_metadata_error_body_is_never_logged_or_retained(
    caplog: pytest.LogCaptureFixture,
) -> None:
    secret = "ecs-response-secret"

    class Transport:
        async def send(self, _request: object) -> object:
            async def content() -> bytes:
                return f'{{"SecretAccessKey":"{secret}"'.encode()

            return SimpleNamespace(status_code=200, content=content())

    class Acquisition:
        async def __aenter__(self) -> Transport:
            return Transport()

        async def __aexit__(self, *_args: object) -> None:
            return None

    class Pool:
        def acquire(self) -> Acquisition:
            return Acquisition()

    async def no_sleep(_delay: float) -> None:
        return None

    fetcher = s3_compatible._SanitizedContainerMetadataFetcher(  # noqa: SLF001
        session=Pool(),  # type: ignore[arg-type]
        sleep=no_sleep,
    )
    provider = s3_compatible._SanitizedContainerProvider(  # noqa: SLF001
        environ={
            "AWS_CONTAINER_CREDENTIALS_RELATIVE_URI": (
                "/v2/credentials/workstream-runtime"
            )
        }
    )
    provider._fetcher = fetcher

    class FakeSession:
        async def get_credentials(self) -> object:
            return await provider.load()

    caplog.set_level("DEBUG")
    with pytest.raises(ArtifactConfigurationError) as caught:
        await s3_compatible.resolve_isolated_aws_workload_credentials(
            FakeSession(),  # type: ignore[arg-type]
            expected_method="container-role",
        )

    assert secret not in caplog.text
    for record in caplog.records:
        assert_secret_not_retained(
            (record.msg, record.args, record.exc_info, record.exc_text),
            secret,
            traceback_module_prefixes=(
                "aiobotocore.credentials",
                "app.adapters.artifacts.s3_compatible",
            ),
        )
    assert_secret_not_retained(
        caught.value,
        secret,
        traceback_module_prefixes=("app.adapters.artifacts.s3_compatible",),
    )


async def test_imds_error_responses_are_never_logged(
    caplog: pytest.LogCaptureFixture,
) -> None:
    secret = "imds-response-secret"
    fetcher = s3_compatible._SanitizedInstanceMetadataFetcher(  # noqa: SLF001
        env={"AWS_EC2_METADATA_V1_DISABLED": "true"},
        config={"ec2_metadata_v1_disabled": True},
    )

    response = SimpleNamespace(
        status_code=500,
        url="http://169.254.169.254/latest/meta-data/iam/security-credentials/",
        content=secret.encode(),
    )
    caplog.set_level("DEBUG")

    assert await fetcher._is_non_ok_response(response) is True  # noqa: SLF001

    async def token() -> str:
        return "imds-v2-token"

    async def role_name(_token: str) -> str:
        return "workstream-role"

    async def credentials(_role_name: str, _token: str) -> dict[str, str]:
        return {"Code": "Error", "Message": secret}

    fetcher._fetch_metadata_token = token  # type: ignore[method-assign]
    fetcher._get_iam_role = role_name  # type: ignore[method-assign]
    fetcher._get_credentials = credentials  # type: ignore[method-assign]
    assert await fetcher.retrieve_iam_role_credentials() == {}

    class FakeRoleFetcher:
        async def retrieve_iam_role_credentials(self) -> dict[str, str]:
            return {
                "role_name": secret,
                "access_key": "access-key",
                "secret_key": "secret-key",
                "token": "session-token",
                "expiry_time": "2099-01-01T00:00:00Z",
            }

    provider = s3_compatible._SanitizedInstanceMetadataProvider(  # noqa: SLF001
        iam_role_fetcher=FakeRoleFetcher()
    )
    assert await provider.load() is not None
    assert secret not in caplog.text
    for record in caplog.records:
        assert_secret_not_retained(
            (record.msg, record.args, record.exc_info, record.exc_text),
            secret,
        )


def test_imds_invalid_expiration_is_never_logged(
    caplog: pytest.LogCaptureFixture,
) -> None:
    secret = "imds-expiration-secret"
    fetcher = s3_compatible._SanitizedInstanceMetadataFetcher(  # noqa: SLF001
        env={"AWS_EC2_METADATA_V1_DISABLED": "true"},
        config={"ec2_metadata_v1_disabled": True},
    )
    credentials = {"expiry_time": secret}
    caplog.set_level("DEBUG")

    fetcher._evaluate_expiration(credentials)  # noqa: SLF001

    assert credentials == {"expiry_time": secret}
    assert secret not in caplog.text
    for record in caplog.records:
        assert_secret_not_retained(
            (record.msg, record.args, record.exc_info, record.exc_text),
            secret,
        )


async def test_sanitized_imds_fetcher_success_paths() -> None:
    async def ready(value: object) -> object:
        return value

    token_response = SimpleNamespace(
        status_code=200,
        text=ready("imds-v2-token"),
    )

    class Transport:
        def __init__(self, response: object) -> None:
            self.response = response

        async def send(self, _request: object) -> object:
            return self.response

    class Acquisition:
        def __init__(self, transport: Transport) -> None:
            self.transport = transport

        async def __aenter__(self) -> Transport:
            return self.transport

        async def __aexit__(self, *_args: object) -> None:
            return None

    class Pool:
        def __init__(self, response: object) -> None:
            self.transport = Transport(response)

        def acquire(self) -> Acquisition:
            return Acquisition(self.transport)

    fetcher = s3_compatible._SanitizedInstanceMetadataFetcher(  # noqa: SLF001
        env={"AWS_EC2_METADATA_V1_DISABLED": "true"},
        config={"ec2_metadata_v1_disabled": True},
        session=Pool(token_response),  # type: ignore[arg-type]
    )
    assert await fetcher._fetch_metadata_token() == "imds-v2-token"  # noqa: SLF001

    metadata_response = SimpleNamespace(status_code=200)
    fetcher._session = Pool(metadata_response)

    async def no_retry(_response: object) -> bool:
        return False

    assert (
        await fetcher._get_request(  # noqa: SLF001
            "latest/meta-data/iam/security-credentials/workstream-role",
            no_retry,
            token="imds-v2-token",
        )
        is metadata_response
    )

    async def token() -> str:
        return "imds-v2-token"

    async def role_name(_token: str) -> str:
        return "workstream-role"

    async def credentials(_role_name: str, _token: str) -> dict[str, str]:
        return {
            "AccessKeyId": "access-key",
            "SecretAccessKey": "secret-key",
            "Token": "session-token",
            "Expiration": "2099-01-01T00:00:00Z",
        }

    fetcher._fetch_metadata_token = token  # type: ignore[method-assign]
    fetcher._get_iam_role = role_name  # type: ignore[method-assign]
    fetcher._get_credentials = credentials  # type: ignore[method-assign]
    assert await fetcher.retrieve_iam_role_credentials() == {
        "role_name": "workstream-role",
        "access_key": "access-key",
        "secret_key": "secret-key",
        "token": "session-token",
        "expiry_time": "2099-01-01T00:00:00Z",
    }


async def test_sanitized_container_provider_success_path() -> None:
    class Fetcher:
        async def retrieve_full_uri(
            self,
            _full_uri: str,
            *,
            headers: dict[str, str],
        ) -> dict[str, str]:
            assert headers == {"Authorization": "Bearer identity-token"}
            return {
                "AccessKeyId": "access-key",
                "SecretAccessKey": "secret-key",
                "Token": "session-token",
                "Expiration": "2099-01-01T00:00:00Z",
                "AccountId": "123456789012",
            }

    provider = s3_compatible._SanitizedContainerProvider(  # noqa: SLF001
        environ={
            "AWS_CONTAINER_CREDENTIALS_FULL_URI": (
                "http://169.254.170.2/v2/credentials/workstream-runtime"
            ),
            "AWS_CONTAINER_AUTHORIZATION_TOKEN": "Bearer identity-token",
        }
    )
    provider._fetcher = Fetcher()
    fetch_credentials = provider._create_fetcher(  # noqa: SLF001
        "http://169.254.170.2/v2/credentials/workstream-runtime"
    )

    assert await fetch_credentials() == {
        "access_key": "access-key",
        "secret_key": "secret-key",
        "token": "session-token",
        "expiry_time": "2099-01-01T00:00:00Z",
        "account_id": "123456789012",
    }


@pytest.mark.parametrize(
    ("status_code", "body", "match"),
    [
        (500, b'{"SecretAccessKey":"provider-secret"}', "non-200"),
        (200, b"[]", "invalid document"),
    ],
)
async def test_sanitized_container_fetcher_rejects_response_shapes(
    status_code: int,
    body: bytes,
    match: str,
) -> None:
    class Transport:
        async def send(self, _request: object) -> object:
            async def content() -> bytes:
                return body

            return SimpleNamespace(status_code=status_code, content=content())

    class Acquisition:
        async def __aenter__(self) -> Transport:
            return Transport()

        async def __aexit__(self, *_args: object) -> None:
            return None

    class Pool:
        def acquire(self) -> Acquisition:
            return Acquisition()

    fetcher = s3_compatible._SanitizedContainerMetadataFetcher(  # noqa: SLF001
        session=Pool(),  # type: ignore[arg-type]
    )

    with pytest.raises(MetadataRetrievalError, match=match):
        await fetcher._get_response(  # noqa: SLF001
            "http://169.254.170.2/v2/credentials/workstream-runtime",
            {"Accept": "application/json"},
            1.0,
        )


async def test_sanitized_container_fetcher_accepts_headers_and_document() -> None:
    observed_headers: dict[str, str] = {}

    class Transport:
        async def send(self, request: object) -> object:
            observed_headers.update(dict(request.headers.items()))

            async def content() -> bytes:
                return b'{"AccessKeyId":"access-key"}'

            return SimpleNamespace(status_code=200, content=content())

    class Acquisition:
        async def __aenter__(self) -> Transport:
            return Transport()

        async def __aexit__(self, *_args: object) -> None:
            return None

    class Pool:
        def acquire(self) -> Acquisition:
            return Acquisition()

    fetcher = s3_compatible._SanitizedContainerMetadataFetcher(  # noqa: SLF001
        session=Pool(),  # type: ignore[arg-type]
    )

    assert await fetcher._retrieve_credentials(  # noqa: SLF001
        "http://169.254.170.2/v2/credentials/workstream-runtime",
        {"Authorization": "Bearer identity-token"},
    ) == {"AccessKeyId": "access-key"}
    assert observed_headers["Authorization"] == "Bearer identity-token"


async def test_sanitized_imds_fetcher_failure_and_empty_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Transport:
        def __init__(self, response: object | None = None) -> None:
            self.response = response
            self.raise_timeout = False

        async def send(self, _request: object) -> object:
            if self.raise_timeout:
                raise ReadTimeoutError(endpoint_url="http://169.254.169.254")
            return self.response

    class Acquisition:
        def __init__(self, transport: Transport) -> None:
            self.transport = transport

        async def __aenter__(self) -> Transport:
            return self.transport

        async def __aexit__(self, *_args: object) -> None:
            return None

    class Pool:
        def __init__(self, transport: Transport) -> None:
            self.transport = transport

        def acquire(self) -> Acquisition:
            return Acquisition(self.transport)

    forbidden = Transport(SimpleNamespace(status_code=403, text="forbidden"))
    fetcher = s3_compatible._SanitizedInstanceMetadataFetcher(  # noqa: SLF001
        env={"AWS_EC2_METADATA_V1_DISABLED": "true"},
        config={"ec2_metadata_v1_disabled": True},
        session=Pool(forbidden),  # type: ignore[arg-type]
    )
    assert await fetcher._fetch_metadata_token() is None  # noqa: SLF001

    timeout = Transport()
    timeout.raise_timeout = True
    fetcher._session = Pool(timeout)
    with pytest.raises(fetcher._RETRIES_EXCEEDED_ERROR_CLS):  # noqa: SLF001
        await fetcher._get_request(  # noqa: SLF001
            "latest/meta-data/iam/security-credentials/workstream-role",
            lambda _response: False,
            token="imds-v2-token",
        )

    async def retries_exceeded() -> str:
        raise fetcher._RETRIES_EXCEEDED_ERROR_CLS()  # noqa: SLF001

    fetcher._fetch_metadata_token = retries_exceeded  # type: ignore[method-assign]
    assert await fetcher.retrieve_iam_role_credentials() == {}

    fetcher._evaluate_expiration({})  # noqa: SLF001
    monkeypatch.setattr(
        s3_compatible,
        "get_current_datetime",
        lambda: datetime.datetime(2026, 1, 1),
    )
    monkeypatch.setattr(s3_compatible.random, "randint", lambda _start, _end: 120)
    expiring = {"expiry_time": "2026-01-01T00:01:00Z"}
    fetcher._evaluate_expiration(expiring)  # noqa: SLF001
    assert expiring["expiry_time"] == "2026-01-01T00:12:00Z"

    class EmptyRoleFetcher:
        async def retrieve_iam_role_credentials(self) -> dict[str, str]:
            return {}

    provider = s3_compatible._SanitizedInstanceMetadataProvider(  # noqa: SLF001
        iam_role_fetcher=EmptyRoleFetcher()
    )
    assert await provider.load() is None
