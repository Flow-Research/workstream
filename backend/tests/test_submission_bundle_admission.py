"""Focused custody and ordering proof for submission-bundle durable intent."""

from __future__ import annotations

from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from app.core.identifiers import new_record_id

import pytest
from starlette.requests import Request

import app.adapters.artifacts as artifact_adapters
from app.core.config import Settings
from app.modules.artifacts.api import (
    SubmissionBundlePreparationRejected,
    SubmissionBundlePreparationRequest,
    SubmissionBundlePreparationResult,
    SubmissionBundlePreparationUnavailable,
)
from app.modules.artifacts.schemas import (
    ArtifactAuthorityDeniedError,
)
from app.interfaces.artifacts import (
    ArtifactConfigurationError,
    ArtifactProviderLiveProofRequiredError,
)
from app.modules.artifacts.submission_authorization import (
    DenySubmissionBundlePreparedAuthorization,
    DenySubmissionBundlePreparationAuthorization,
)
from app.modules.artifacts.submission_admission import (
    SubmissionBundleDurablePutResult,
)
from app.modules.artifacts.submission_admission import (
    PreparedSubmissionBundlePreparationCommand,
)
from app.modules.authorization.api import ActorIdentityFacts, ActorKind
from app.modules.authorization.prepared import PreparedAuthorizationHandle
from app.modules.artifacts.api.submission_preparation import public_pre_submission_results
from tests.artifact_store_helpers import artifact_byte_stream
from tests.test_submission_bundle_preparation_recovery import _feedback_facts
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


def _sha(character: str) -> str:
    return "sha256:" + character * 64


@pytest.mark.asyncio
async def test_artifact_adapter_preserves_public_actor_facts() -> None:
    actor = _actor()

    assert await artifact_adapters.get_submission_bundle_preparation_actor(actor) is actor


@pytest.mark.asyncio
async def test_explicit_deny_preparation_authority_denies() -> None:
    from app.modules.artifacts.submission_authorization import (
        DenySubmissionBundlePreparationAuthorization,
    )

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


def test_artifact_adapter_rejects_unproven_aws_runtime() -> None:
    settings = SimpleNamespace(
        artifact_store_backend="s3_compatible", artifact_s3_provider_profile="aws_s3"
    )

    with pytest.raises(ArtifactProviderLiveProofRequiredError):
        artifact_adapters.create_artifact_store_bootstrap(  # type: ignore[arg-type]
            settings,
            activation_guard=None,
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

    bootstrap = artifact_adapters.create_artifact_store_bootstrap(settings, activation_guard=None)

    try:
        assert bootstrap.identity.provider_key == "local"
        assert bootstrap.namespace_identity.provider_profile == "local-v2"
    finally:
        bootstrap.close()


def test_artifact_adapter_composes_submission_command_from_owner_ports(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request_id = new_record_id()
    correlation_id = new_record_id()
    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/hidden",
            "headers": [],
            "state": {
                "request_id": str(request_id),
                "correlation_id": str(correlation_id),
            },
        }
    )
    request.scope["app"] = SimpleNamespace(
        state=SimpleNamespace(
            settings=Settings(),
        )
    )
    session = object()
    internal_authority = object()
    authority = SimpleNamespace(close=Mock())
    task_contexts = object()
    project_contexts = object()
    monkeypatch.setattr(
        artifact_adapters, "task_submission_context_port", Mock(return_value=task_contexts)
    )
    monkeypatch.setattr(
        artifact_adapters,
        "project_locked_policy_context_port",
        Mock(return_value=project_contexts),
    )

    command = artifact_adapters.get_submission_bundle_preparation_command(
        request,
        session,  # type: ignore[arg-type]
        internal_authority,  # type: ignore[arg-type]
        authority,
    )

    assert command._session is session
    assert command._authority is authority
    assert command._task_contexts is task_contexts
    assert command._project_contexts is project_contexts
    artifact_adapters.task_submission_context_port.assert_called_once_with(session)
    artifact_adapters.project_locked_policy_context_port.assert_called_once_with(session)


def test_submission_bundle_preparation_is_public_binary_contract() -> None:
    from fastapi import FastAPI

    app = create_app()
    route = next(
        route
        for route in submission_router.routes
        if getattr(route, "name", None) == "prepare_submission_bundle"
    )
    assert route.include_in_schema is True
    mounted = app.url_path_for("prepare_submission_bundle", task_id=str(new_record_id()))
    assert str(mounted).startswith("/api/v1/tasks/")
    assert str(mounted).endswith("/submission-bundle-preparations")
    assert route.methods == {"POST"}
    schema_app = FastAPI()
    schema_app.include_router(submission_router, prefix="/api/v1")
    operation = schema_app.openapi()["paths"]["/api/v1/tasks/{task_id}/submission-bundle-preparations"]["post"]
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


@asynccontextmanager
async def _transaction():
    yield


@pytest.mark.asyncio
async def test_hidden_preparation_denies_before_reading_uploaded_bytes() -> None:
    reads = 0

    async def bytes_source():
        nonlocal reads
        reads += 1
        yield b"PK\x03\x04must-not-be-read"

    def runtime_factory():
        raise AssertionError("runtime must not open before contributor preflight")

    command = PreparedSubmissionBundlePreparationCommand(
        session=SimpleNamespace(),
        authority=DenySubmissionBundlePreparationAuthorization(),
        task_contexts=SimpleNamespace(),
        project_contexts=SimpleNamespace(),
        runtime_factory=runtime_factory,
    )
    with pytest.raises(SubmissionBundlePreparationUnavailable):
        await command.prepare(
            _preparation_request(
                byte_source=bytes_source(),
                summary="caf\N{LATIN SMALL LETTER E WITH ACUTE}",
            )
        )
    assert reads == 0


@pytest.mark.asyncio
async def test_hidden_preparation_closes_authority_after_invalid_media_type() -> None:
    authority = SimpleNamespace(
        preflight=AsyncMock(),
        close=Mock(),
    )
    command = PreparedSubmissionBundlePreparationCommand(
        session=SimpleNamespace(),
        authority=authority,
        task_contexts=SimpleNamespace(),
        project_contexts=SimpleNamespace(),
        runtime_factory=Mock(side_effect=AssertionError("runtime must stay closed")),
    )
    with pytest.raises(
        SubmissionBundlePreparationRejected,
        match="submission_bundle_media_type_invalid",
    ):
        await command.prepare(
            _preparation_request(
                byte_source=artifact_byte_stream(b"{}"), media_type="application/json"
            )
        )
    authority.close.assert_called_once_with()


@pytest.mark.asyncio
@pytest.mark.parametrize("denied_phase", ("actor", "grant"))
async def test_authority_denial_preserves_task_actor_project_grant_order(denied_phase) -> None:
    events = []
    denial = ArtifactAuthorityDeniedError("submission bundle preparation is unavailable")

    def phase(name):
        async def invoke(*_args, **_kwargs):
            events.append(name)
            if name == denied_phase:
                raise denial
            return object()

        return invoke

    authority = SimpleNamespace(
        lock_actor=AsyncMock(side_effect=phase("actor")),
        revalidate=AsyncMock(side_effect=phase("grant")),
    )
    references = SimpleNamespace(
        project_id=new_record_id(), guide_version="v1",
        source_snapshot_id=new_record_id(), source_snapshot_hash=_sha("1"),
        effective_policy_id=new_record_id(), effective_policy_hash=_sha("2"),
        pre_submit_policy_id=new_record_id(), pre_submit_policy_bundle_hash=_sha("3"),
    )
    task = SimpleNamespace(locked_project_context=references)
    async def lock_task(*args):
        events.append("task")
        return task
    project_contexts = SimpleNamespace(lock_locked_policy_context=AsyncMock(side_effect=phase("project")))
    command = PreparedSubmissionBundlePreparationCommand(
        session=SimpleNamespace(), authority=authority,
        task_contexts=SimpleNamespace(lock_submission_context=AsyncMock(side_effect=lock_task)),
        project_contexts=project_contexts, runtime_factory=Mock(),
    )
    with pytest.raises(ArtifactAuthorityDeniedError) as caught:
        await command._lock_authorized_context(_preparation_request(byte_source=object()))
    assert caught.value is denial
    assert events == (
        ["task", "actor"] if denied_phase == "actor" else ["task", "actor", "project", "grant"]
    )
    command._runtime_factory.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "admission_status,expected_status",
    (
        ("ready", "ready"),
        ("stale", "stale"),
        ("consumed", "conflict"),
    ),
)
async def test_selected_replay_projects_current_admission_state(
    admission_status,
    expected_status,
) -> None:
    attempt_id = new_record_id()
    admission_id = new_record_id()
    row_result = SimpleNamespace(
        one_or_none=lambda: (
            SimpleNamespace(id=str(new_record_id())),
            SimpleNamespace(id=str(attempt_id), status="object_confirmed"),
            SimpleNamespace(id=str(admission_id), status=admission_status),
        )
    )
    session = SimpleNamespace(begin=_transaction, execute=AsyncMock(return_value=row_result))
    command = PreparedSubmissionBundlePreparationCommand(
        session=session,
        authority=SimpleNamespace(),
        task_contexts=SimpleNamespace(),
        project_contexts=SimpleNamespace(),
        runtime_factory=Mock(),
    )

    execution = _feedback_facts(eligible=True)
    result = await command._selected_replay_result(SimpleNamespace(
        run_id=new_record_id(), status="completed",
        terminal=SimpleNamespace(outcome="completed", execution=execution),
    ))

    # Exact replay returns the retained intake feedback, not a fresh check.
    assert result == SubmissionBundlePreparationResult(
        put_attempt_id=attempt_id,
        admission_id=admission_id if admission_status == "ready" else None,
        submission_bundle_preparation_status=expected_status,
        replayed=True,
        pre_submission_results=tuple(public_pre_submission_results(execution)),
    )


@pytest.mark.parametrize(
    "durable_status",
    (
        "prepared",
        "put_in_flight",
        "object_confirmed",
        "stored_pending_verification",
        "observed_confirmed",
        "acknowledgement_unknown",
        "provider_unavailable",
        "conflict",
        "integrity_mismatch",
        "missing",
        "absent_replay_required",
        "stale",
        "ready",
    ),
)
def test_durable_put_result_projects_every_closed_preparation_status(
    durable_status: str,
) -> None:
    durable = SubmissionBundleDurablePutResult(
        put_attempt_id=new_record_id(),
        selected_pre_submit_run_id=new_record_id(),
        operation_identity=_sha("9"),
        admission_id=None,
        status=durable_status,
        replayed=True,
    )
    execution = _feedback_facts(eligible=True)
    assert PreparedSubmissionBundlePreparationCommand._result(durable, execution) == (
        SubmissionBundlePreparationResult(
            put_attempt_id=durable.put_attempt_id,
            admission_id=None,
            submission_bundle_preparation_status=durable_status,
            replayed=True,
            pre_submission_results=tuple(public_pre_submission_results(execution)),
        )
    )


@pytest.mark.asyncio
async def test_deny_submission_authority_fails_closed() -> None:
    with pytest.raises(ArtifactAuthorityDeniedError):
        await DenySubmissionBundlePreparedAuthorization().consume(
            prepared_authorization=object.__new__(PreparedAuthorizationHandle),
            facts=object(),
        )
