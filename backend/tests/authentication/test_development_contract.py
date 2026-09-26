from __future__ import annotations


import pytest  # type: ignore[import-not-found]

from app.adapters.auth.dev import DevelopmentAuthVerifier
from app.adapters.auth.flow import (
    FlowAuthVerifier,
)
from app.core.config import Settings


from tests.authentication.support import production_verifier_settings


@pytest.mark.parametrize("changed_field", ["subject", "issuer"])
async def test_verification_preserves_exact_subject_and_issuer(changed_field) -> None:
    first = Settings(
        environment="local",
        auth_provider="dev",
        dev_auth_token="local-token",
        dev_auth_subject="same-subject",
        dev_auth_issuer="same-issuer",
    )
    alternate = {
        "subject": "other-subject",
        "issuer": "other-issuer",
    }
    second = first.model_copy(update={f"dev_auth_{changed_field}": alternate[changed_field]})

    first_verifier = DevelopmentAuthVerifier(first)
    second_verifier = DevelopmentAuthVerifier(second)
    assert first.dev_auth_token is not None
    assert second.dev_auth_token is not None
    first_result = await first_verifier.verify(first.dev_auth_token)
    second_result = await second_verifier.verify(second.dev_auth_token)

    assert first_verifier.canonical_issuer() == first_result.token.issuer == "same-issuer"
    assert (
        second_verifier.canonical_issuer()
        == second_result.token.issuer
        == ("other-issuer" if changed_field == "issuer" else "same-issuer")
    )
    assert (first_result.token.issuer, first_result.token.subject) == ("same-issuer", "same-subject")
    assert ((first_result.token.issuer, first_result.token.subject) ==
            (second_result.token.issuer, second_result.token.subject)) is False
    assert set(first_result.model_dump()) == {"token"}


@pytest.mark.parametrize("environment", ["production", "prod", "staging", "preview"])
def test_dev_auth_requires_explicit_development_environment(environment: str) -> None:
    settings = Settings(
        environment=environment,
        auth_provider="dev",
        dev_auth_token="local-token",
        dev_auth_subject="subject",
        dev_auth_issuer="issuer",
    )

    with pytest.raises(RuntimeError, match="development auth cannot run in production"):
        DevelopmentAuthVerifier(settings)


@pytest.mark.parametrize("environment", ["local", "dev", "development", "test"])
async def test_dev_auth_allows_only_development_environments(environment: str) -> None:
    verifier = DevelopmentAuthVerifier(
        Settings(
            environment=environment,
            auth_provider="dev",
            dev_auth_token="local-token",
            dev_auth_subject="subject",
            dev_auth_issuer="issuer",
        )
    )

    result = await verifier.verify("local-token")
    assert result.token.subject == "subject"
    assert result.token.issuer == "issuer"
    assert result.token.subject_kind == "human"


@pytest.mark.parametrize(
    ("field_name", "error_message"),
    [
        ("dev_auth_token", "WORKSTREAM_DEV_AUTH_TOKEN must be set"),
        ("dev_auth_subject", "WORKSTREAM_DEV_AUTH_SUBJECT must be set"),
        ("dev_auth_issuer", "WORKSTREAM_DEV_AUTH_ISSUER must be set"),
    ],
)
def test_dev_auth_requires_explicit_identity_fields(
    field_name: str,
    error_message: str,
) -> None:
    values: dict[str, str | None] = {
        "environment": "local",
        "auth_provider": "dev",
        "dev_auth_token": "local-token",
        "dev_auth_subject": "subject",
        "dev_auth_issuer": "issuer",
    }
    values[field_name] = None
    settings = Settings(**values)

    with pytest.raises(RuntimeError, match=error_message):
        DevelopmentAuthVerifier(settings)


@pytest.mark.parametrize(
    ("field_name", "error_message"),
    [
        ("dev_auth_subject", "WORKSTREAM_DEV_AUTH_SUBJECT must be set"),
        ("dev_auth_issuer", "WORKSTREAM_DEV_AUTH_ISSUER must be set"),
    ],
)
def test_dev_auth_rejects_whitespace_only_identity_anchors(
    field_name: str,
    error_message: str,
) -> None:
    values = {
        "environment": "local",
        "auth_provider": "dev",
        "dev_auth_token": "local-token",
        "dev_auth_subject": "subject",
        "dev_auth_issuer": "issuer",
    }
    values[field_name] = " \t "

    with pytest.raises(RuntimeError, match=error_message):
        DevelopmentAuthVerifier(Settings(**values))


@pytest.mark.parametrize("field_name", ["dev_auth_subject", "dev_auth_issuer"])
def test_dev_auth_rejects_surrounding_identity_anchor_whitespace(field_name: str) -> None:
    values = {
        "environment": "local",
        "auth_provider": "dev",
        "dev_auth_token": "local-token",
        "dev_auth_subject": "subject",
        "dev_auth_issuer": "issuer",
    }
    values[field_name] = f" {values[field_name]} "

    with pytest.raises(RuntimeError, match=f"WORKSTREAM_{field_name.upper()}"):
        DevelopmentAuthVerifier(Settings(**values))


def test_dev_auth_rejects_issuer_above_persisted_utf8_bound() -> None:
    with pytest.raises(RuntimeError, match="WORKSTREAM_DEV_AUTH_ISSUER"):
        DevelopmentAuthVerifier(
            Settings(
                environment="local",
                auth_provider="dev",
                dev_auth_token="local-token",
                dev_auth_subject="subject",
                dev_auth_issuer="é" * 101,
            )
        )


def test_local_hmac_rejects_issuer_above_persisted_utf8_bound() -> None:
    with pytest.raises(RuntimeError, match="WORKSTREAM_FLOW_AUTH_ISSUER"):
        FlowAuthVerifier(
            Settings(
                environment="test",
                auth_provider="flow",
                flow_auth_issuer="é" * 101,
                flow_auth_audience="workstream",
                flow_auth_local_hmac_secret="local-secret",
            )
        )


def test_flow_rejects_issuer_above_persisted_utf8_bound() -> None:
    with pytest.raises(RuntimeError, match="WORKSTREAM_TOKEN_ISSUER"):
        FlowAuthVerifier(
            production_verifier_settings(
                token_issuer="https://issuer.example.test/" + "é" * 100,
            )
        )


async def test_flow_auth_verifier_boundary_rejects_unconfigured_verification() -> None:
    with pytest.raises(RuntimeError, match="WORKSTREAM_TOKEN_ISSUER"):
        FlowAuthVerifier(Settings(auth_provider="flow"))
