"""Focused custody and ordering proof for submission-bundle durable intent."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from app.core.identifiers import new_record_id

import pytest

import app.adapters.artifacts as artifact_adapters
from app.core.config import Settings
from app.modules.artifacts.api import (
    SubmissionBundlePreparationRejected,
    SubmissionBundlePreparationRequest,
)
from app.modules.artifacts.schemas import (
    ArtifactAuthorityDeniedError,
)
from app.interfaces.artifacts import (
    ArtifactConfigurationError,
)
from app.modules.artifacts.submission_authorization import (
    DenySubmissionBundlePreparedAuthorization,
    DenySubmissionBundlePreparationAuthorization,
)
from app.modules.authorization.api import ActorIdentityFacts, ActorKind
from app.modules.authorization.prepared import PreparedAuthorizationHandle
from tests.artifact_store_helpers import artifact_admission_limit_settings
from app.main import create_app
from app.api.routes.artifact_submissions import router as submission_router
from app.modules.artifacts.submission_admission import validate_submission_packet_headers


def _actor() -> ActorIdentityFacts:
    return ActorIdentityFacts(
        actor_profile_id=new_record_id(),
        identity_link_id=new_record_id(),
        actor_kind=ActorKind.HUMAN,
    )


def _preparation_request(
    *, byte_source, media_type: str = "application/zip", summary: str = "summary"
):
    return SubmissionBundlePreparationRequest(
        actor=_actor(),
        request_id=new_record_id(),
        correlation_id=new_record_id(),
        task_id=new_record_id(),
        assignment_id=new_record_id(),
        predecessor_submission_id=None,
        idempotency_key=new_record_id(),
        summary=summary,
        contributor_attestation="attestation",
        media_type=media_type,
        byte_source=byte_source,
    )


@pytest.mark.asyncio
async def test_artifact_adapter_preserves_public_actor_facts() -> None:
    actor = _actor()

    assert await artifact_adapters.get_submission_bundle_preparation_actor(actor) is actor


@pytest.mark.asyncio
async def test_explicit_deny_preparation_authority_denies() -> None:

    authority = DenySubmissionBundlePreparationAuthorization()
    request = _preparation_request(byte_source=object())

    with pytest.raises(ArtifactAuthorityDeniedError):
        await authority.preflight(request=request)
    with pytest.raises(ArtifactAuthorityDeniedError):
        await authority.lock_actor(request=request)
    with pytest.raises(ArtifactAuthorityDeniedError):
        await authority.revalidate(request=request, project_id=new_record_id())
    with pytest.raises(ArtifactAuthorityDeniedError):
        authority.transaction()
    with pytest.raises(ArtifactAuthorityDeniedError):
        await authority.prepare_final(request=request)
    authority.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("active,nested", ((False, False), (True, True)))
async def test_actor_prelock_requires_a_root_transaction(active, nested) -> None:
    from app.modules.artifacts.authorization import PreparedSubmissionBundlePreparationAuthorization

    authority = object.__new__(PreparedSubmissionBundlePreparationAuthorization)
    authority._session = SimpleNamespace(
        in_transaction=lambda: active,
        in_nested_transaction=lambda: nested,
    )
    authority._repository = SimpleNamespace(lock_request_actor=AsyncMock())
    with pytest.raises(ArtifactAuthorityDeniedError):
        await authority.lock_actor(request=object())
    authority._repository.lock_request_actor.assert_not_awaited()


@pytest.mark.asyncio
async def test_explicit_deny_durable_authority_denies_final_preparation() -> None:
    authority = DenySubmissionBundlePreparedAuthorization()

    with pytest.raises(ArtifactAuthorityDeniedError):
        await authority.prepare_final(facts=object())  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_artifact_adapter_stale_scratch_cleanup_closes_manager(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager = SimpleNamespace(cleanup_stale=AsyncMock(return_value=3), close=Mock())
    monkeypatch.setattr(
        artifact_adapters,
        "create_artifact_scratch_manager",
        lambda _settings: manager,
    )

    assert await artifact_adapters.cleanup_stale_artifact_scratch(Settings()) == 3
    manager.cleanup_stale.assert_awaited_once_with()
    manager.close.assert_called_once_with()


def test_artifact_adapter_maps_preparation_limits_from_settings() -> None:
    settings = Settings()

    preparation = artifact_adapters.artifact_preparation_limits(settings)
    archive = artifact_adapters.submission_archive_limits(settings)

    assert preparation.maximum_source_bytes == settings.artifact_maximum_bytes
    assert preparation.maximum_files == settings.artifact_scratch_maximum_files
    assert preparation.stream_buffer_bytes == settings.artifact_stream_buffer_bytes
    assert archive.maximum_entries == settings.artifact_submission_zip_maximum_entries
    assert archive.maximum_entry_bytes == settings.artifact_submission_zip_maximum_entry_bytes
    assert (
        archive.maximum_compression_ratio
        == settings.artifact_submission_zip_maximum_compression_ratio
    )


def test_artifact_adapter_requires_configured_scratch_root() -> None:
    settings = Settings()
    settings.artifact_scratch_root = None

    with pytest.raises(ArtifactConfigurationError):
        artifact_adapters.create_artifact_scratch_manager(settings)


def test_artifact_adapter_builds_configured_local_bootstrap(tmp_path) -> None:
    root = tmp_path / "objects"
    root.mkdir(mode=0o700)
    settings = Settings(
        _env_file=None,
        **artifact_admission_limit_settings(),
        environment="test",
        artifact_store_backend="local",
        artifact_local_root=root,
        artifact_scratch_root=tmp_path / "scratch",
        artifact_scratch_minimum_free_bytes=0,
    )

    bootstrap = artifact_adapters.create_artifact_store_bootstrap(settings)

    try:
        assert bootstrap.identity.provider_key == "local"
        assert bootstrap.namespace_identity.provider_profile == "local-v2"
    finally:
        bootstrap.close()


def test_submission_is_public_binary_contract() -> None:
    from fastapi import FastAPI

    app = create_app()
    route = next(
        route
        for route in submission_router.routes
        if getattr(route, "name", None) == "submit_source"
    )
    assert route.include_in_schema is True
    mounted = app.url_path_for("submit_source", task_id=str(new_record_id()))
    assert str(mounted).startswith("/api/v1/tasks/")
    assert str(mounted).endswith("/submissions")
    assert route.methods == {"POST"}
    schema_app = FastAPI()
    schema_app.include_router(submission_router, prefix="/api/v1")
    operation = schema_app.openapi()["paths"]["/api/v1/tasks/{task_id}/submissions"]["post"]
    assert operation["requestBody"]["content"]["application/zip"]["schema"] == {
        "type": "string", "format": "binary",
    }
    required_headers = {parameter["name"] for parameter in operation["parameters"]
                        if parameter["in"] == "header" and parameter["required"]}
    assert {"X-Task-Assignment-Id", "Idempotency-Key"} <= required_headers
    assert operation["responses"]["202"] and operation["responses"]["422"]


def test_submission_packet_headers_reject_non_ascii() -> None:
    validate_submission_packet_headers("plain summary", "plain attestation")
    with pytest.raises(
        SubmissionBundlePreparationRejected,
        match="submission_bundle_packet_header_encoding_invalid",
    ):
        validate_submission_packet_headers("caf\N{LATIN SMALL LETTER E WITH ACUTE}", "ok")


@pytest.mark.asyncio
async def test_deny_submission_authority_fails_closed() -> None:
    with pytest.raises(ArtifactAuthorityDeniedError):
        await DenySubmissionBundlePreparedAuthorization().consume(
            prepared_authorization=object.__new__(PreparedAuthorizationHandle),
            facts=object(),
        )
