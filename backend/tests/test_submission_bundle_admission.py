"""Focused custody and ordering proof for submission-bundle durable intent."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from fastapi import HTTPException
from starlette.requests import Request

import app.adapters.artifacts as artifact_adapters
import app.modules.artifacts.submission_admission as submission_admission_module
from app.core.config import Settings
from app.modules.artifacts.pre_submit_evidence import (
    PreSubmitEvidenceConflict,
    PreSubmitEvidenceService,
    PreSubmitPassCapability,
)
from app.modules.artifacts.api import (
    SubmissionBundlePreparationRejected,
    SubmissionBundlePreparationRequest,
    SubmissionBundlePreparationResult,
    SubmissionBundlePreparationUnavailable,
)
from app.modules.artifacts.preparation import ArtifactPreparationService, ArtifactScratchManager
from app.modules.artifacts.schemas import (
    ArtifactAdmissionResult,
    ArtifactAuthorityDeniedError,
    SubmissionBundleArtifactAdmissionRequest,
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
    SubmissionBundleDurablePutRequest,
    SubmissionBundleDurablePutResult,
    SubmissionBundleDurablePutService,
)
from app.modules.artifacts.submission_materialization import (
    PreparedBundlePreSubmitEvidenceService,
)
from app.modules.artifacts.submission_admission import (
    SubmissionBundleAdmissionPublicationError,
    SubmissionBundleAdmissionPublisher,
)
from app.modules.artifacts.service import ArtifactAdmissionService
from app.modules.artifacts.submission_custody import SubmissionBundlePreparedCustody
from app.modules.artifacts.submission_admission import (
    PreparedSubmissionBundlePreparationCommand,
)
from app.modules.authorization.api import ActorIdentityFacts, ActorKind
from app.modules.authorization.prepared import PreparedAuthorizationHandle
from tests.artifact_store_helpers import artifact_byte_stream, artifact_preparation_limits
from tests.artifact_store_helpers import artifact_admission_limit_settings
from app.main import create_app
from app.api.routes.artifact_submissions import prepare_submission_bundle, router as submission_router
from app.modules.artifacts.submission_admission import validate_submission_packet_headers


def _actor() -> ActorIdentityFacts:
    return ActorIdentityFacts(
        actor_profile_id=uuid4(),
        identity_link_id=uuid4(),
        actor_kind=ActorKind.HUMAN,
    )


def _preparation_request(
    *, byte_source, media_type: str = "application/zip", summary: str = "summary"
):
    return SubmissionBundlePreparationRequest(
        actor=_actor(),
        request_id=uuid4(),
        correlation_id=uuid4(),
        task_id=uuid4(),
        assignment_id=uuid4(),
        predecessor_submission_id=None,
        idempotency_key=uuid4(),
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
        await authority.revalidate(request=request, project_id=uuid4())
    with pytest.raises(ArtifactAuthorityDeniedError):
        authority.transaction()
    with pytest.raises(ArtifactAuthorityDeniedError):
        await authority.prepare_final(request=request)
    authority.close()


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
        artifact_adapters.require_artifact_runtime_eligible(settings)  # type: ignore[arg-type]


def test_artifact_adapter_requires_configured_scratch_root() -> None:
    settings = Settings()
    settings.artifact_scratch_root = None

    with pytest.raises(ArtifactConfigurationError):
        artifact_adapters.create_artifact_scratch_manager(settings)


def test_artifact_adapter_builds_configured_local_bootstrap(tmp_path) -> None:
    root = tmp_path / "objects"
    root.mkdir(mode=0o700)
    settings = Settings(
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


def test_artifact_adapter_composes_submission_command_from_owner_ports(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request_id = uuid4()
    correlation_id = uuid4()
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
            pre_submission_checker_catalogue=object(),
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


def test_submission_bundle_preparation_route_is_hidden() -> None:
    app = create_app()
    route = next(
        route
        for route in submission_router.routes
        if getattr(route, "name", None) == "prepare_submission_bundle"
    )
    assert route.include_in_schema is False
    mounted = app.url_path_for("prepare_submission_bundle", task_id=str(uuid4()))
    assert str(mounted).startswith("/api/v1/tasks/")
    assert str(mounted).endswith("/submission-bundle-preparations")
    assert route.methods == {"POST"}
    assert "/api/v1/tasks/{task_id}/submission-bundle-preparations" not in app.openapi()["paths"]


def test_submission_packet_headers_reject_non_ascii() -> None:
    validate_submission_packet_headers("plain summary", "plain attestation")
    with pytest.raises(
        SubmissionBundlePreparationRejected,
        match="submission_bundle_packet_header_encoding_invalid",
    ):
        validate_submission_packet_headers(
            "caf\N{LATIN SMALL LETTER E WITH ACUTE}", "ok"
        )


@pytest.mark.asyncio
async def test_hidden_preparation_maps_locked_context_race_to_bounded_conflict() -> None:
    command = SimpleNamespace(
        prepare=AsyncMock(
            side_effect=SubmissionBundlePreparationRejected(
                "submission_bundle_preparation_context_changed"
            )
        )
    )
    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/",
            "headers": [(b"content-type", b"application/zip")],
        }
    )

    with pytest.raises(HTTPException) as failure:
        await prepare_submission_bundle(
            task_id=str(uuid4()),
            request=request,
            actor=_actor(),
            command=command,
            assignment_id=str(uuid4()),
            idempotency_key=str(uuid4()),
            summary="summary",
            contributor_attestation="attestation",
        )

    assert failure.value.status_code == 409
    assert failure.value.detail == "submission_bundle_preparation_context_changed"


@asynccontextmanager
async def _transaction():
    yield


async def _prepared(tmp_path):
    manager = ArtifactScratchManager(
        root=tmp_path / "scratch",
        limits=artifact_preparation_limits(),
    )
    prepared = await ArtifactPreparationService(manager).prepare(
        artifact_byte_stream(b"PK\x03\x04checked submission"),
        media_type="application/zip",
    )
    return manager, prepared


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
async def test_post_byte_authority_denial_precedes_evidence_relock() -> None:
    denial = ArtifactAuthorityDeniedError("submission bundle preparation is unavailable")
    authority = SimpleNamespace(revalidate=AsyncMock(side_effect=denial))
    task_contexts = SimpleNamespace(lock_submission_context=AsyncMock())
    project_contexts = SimpleNamespace(lock_locked_policy_context=AsyncMock())
    session = SimpleNamespace(
        in_transaction=lambda: False,
        begin=_transaction,
        execute=AsyncMock(),
    )
    workflow = PreparedBundlePreSubmitEvidenceService(
        session=session,
        materialization=SimpleNamespace(),
        preparation_authorization=authority,
        task_contexts=task_contexts,
        project_contexts=project_contexts,
    )
    materialization_request = SimpleNamespace(
        prepared_artifact=SimpleNamespace(
            commitment=SimpleNamespace(sha256=_sha("1"), byte_count=1),
            generation_id=uuid4(),
        ),
    )

    with pytest.raises(ArtifactAuthorityDeniedError):
        await workflow.persist(
            materialization_request,
            execution=object(),
            preparation_request=object(),
        )

    authority.revalidate.assert_awaited_once()
    task_contexts.lock_submission_context.assert_not_awaited()
    project_contexts.lock_locked_policy_context.assert_not_awaited()


@pytest.mark.asyncio
async def test_existing_durable_preparation_projects_exact_ready_admission() -> None:
    attempt_id = uuid4()
    admission_id = uuid4()
    row_result = SimpleNamespace(
        one_or_none=lambda: (
            SimpleNamespace(id=str(uuid4())),
            SimpleNamespace(id=str(attempt_id), status="object_confirmed"),
            SimpleNamespace(id=str(admission_id)),
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

    result = await command._existing_durable_result(uuid4())

    assert result == SubmissionBundlePreparationResult(
        put_attempt_id=attempt_id,
        admission_id=admission_id,
        submission_bundle_preparation_status="ready",
        replayed=True,
    )


@pytest.mark.asyncio
async def test_hidden_preparation_replays_persisted_checked_custody(monkeypatch) -> None:
    actor_id = uuid4()
    task_id = uuid4()
    assignment_id = uuid4()
    evidence_id = uuid4()
    expected = SubmissionBundlePreparationResult(
        put_attempt_id=uuid4(),
        admission_id=uuid4(),
        submission_bundle_preparation_status="ready",
        replayed=True,
    )
    locked = SimpleNamespace(effective_policy_id=uuid4(), pre_submit_policy_id=uuid4())
    prepared = SimpleNamespace(
        commitment=object(),
        inspect=AsyncMock(return_value=object()),
        close=AsyncMock(),
    )
    events: list[str] = []

    async def prepare_bytes(*_args, **_kwargs):
        events.append("prepare_bytes")
        return prepared

    async def revalidate(**_kwargs):
        events.append("revalidate")

    runtime = SimpleNamespace(
        preparation=SimpleNamespace(prepare=AsyncMock(side_effect=prepare_bytes)),
        inspector=object(),
        catalogue=object(),
        materialization=SimpleNamespace(prepare_authorization=AsyncMock(return_value=object())),
        evidence=SimpleNamespace(
            materialize=AsyncMock(return_value=object()),
            persist=AsyncMock(
                return_value=SimpleNamespace(
                    evidence=SimpleNamespace(evidence_set_id=evidence_id),
                    pass_capability=None,
                )
            ),
        ),
        durable_put=object(),
    )

    @asynccontextmanager
    async def runtime_factory():
        yield runtime

    monkeypatch.setattr(
        submission_admission_module,
        "build_submission_manifest",
        Mock(return_value=object()),
    )
    monkeypatch.setattr(
        submission_admission_module,
        "evaluate_submission_change",
        Mock(return_value=object()),
    )
    project_id = uuid4()
    authority = SimpleNamespace(
        preflight=AsyncMock(), revalidate=AsyncMock(side_effect=revalidate), close=Mock()
    )
    command = PreparedSubmissionBundlePreparationCommand(
        session=SimpleNamespace(begin=_transaction),
        authority=authority,
        task_contexts=SimpleNamespace(),
        project_contexts=SimpleNamespace(),
        runtime_factory=runtime_factory,
    )
    command._lock_context = AsyncMock(
        return_value=(
            SimpleNamespace(
                predecessor=None,
                locked_project_context=SimpleNamespace(project_id=project_id),
            ),
            locked,
        )
    )
    command._compile_plan = Mock(return_value=object())
    command._load_predecessor = AsyncMock(return_value=None)
    command._existing_durable_result = AsyncMock(return_value=expected)

    request = SubmissionBundlePreparationRequest(
            actor=ActorIdentityFacts(
                actor_profile_id=actor_id,
                identity_link_id=uuid4(),
                actor_kind=ActorKind.HUMAN,
            ),
            request_id=uuid4(),
            correlation_id=uuid4(),
            task_id=task_id,
            assignment_id=assignment_id,
            predecessor_submission_id=None,
            idempotency_key=uuid4(),
            summary="summary",
            contributor_attestation="attestation",
            media_type="application/zip",
            byte_source=artifact_byte_stream(b"PK\x03\x04replay"),
        )
    result = await command.prepare(request)

    assert result == expected
    runtime.preparation.prepare.assert_awaited_once()
    authority.revalidate.assert_awaited_once_with(request=request, project_id=project_id)
    assert events[:2] == ["revalidate", "prepare_bytes"]
    runtime.evidence.materialize.assert_awaited_once()
    runtime.evidence.persist.assert_awaited_once()
    prepared.close.assert_awaited_once()
    authority.close.assert_called_once_with()


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
        put_attempt_id=uuid4(),
        pre_submit_evidence_set_id=uuid4(),
        operation_identity=_sha("9"),
        admission_id=None,
        status=durable_status,
        replayed=True,
    )
    assert PreparedSubmissionBundlePreparationCommand._result(durable) == (
        SubmissionBundlePreparationResult(
            put_attempt_id=durable.put_attempt_id,
            admission_id=None,
            submission_bundle_preparation_status=durable_status,
            replayed=True,
        )
    )


def test_post_byte_locked_context_conflict_maps_to_public_race_code() -> None:
    conflict = PreSubmitEvidenceConflict("pre_submit_locked_context_changed")
    assert (
        PreparedSubmissionBundlePreparationCommand._evidence_conflict_code(conflict)
        == "submission_bundle_preparation_context_changed"
    )

def _capability(prepared, evidence_set_id):
    service = PreSubmitEvidenceService(
        SimpleNamespace(),
        task_contexts=SimpleNamespace(),
        project_contexts=SimpleNamespace(),
    )
    return service._mint_pass_capability(
        evidence_set_id=evidence_set_id,
        prepared_generation_id=prepared.generation_id,
        predecessor_submission_id=None,
        effective_plan_sha256=_sha("7"),
        archive_sha256=prepared.commitment.sha256,
        semantic_manifest_sha256=_sha("2"),
        storage_scheme="s3",
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("observed_confirmation", [False, True])
async def test_verified_submission_lineage_publishes_one_ready_admission(
    observed_confirmation: bool,
) -> None:
    attempt_id = str(uuid4())
    replica_id = str(uuid4())
    content_id = str(uuid4())
    job_id = str(uuid4())
    receipt_id = str(uuid4())
    evidence_id = str(uuid4())
    digest = _sha("1")
    evidence = SimpleNamespace(
        id=evidence_id,
        terminal_status="passed",
        eligible=True,
        archive_sha256=digest,
        archive_byte_count=25,
        actor_profile_id=str(uuid4()),
        identity_link_id=str(uuid4()),
        project_id=str(uuid4()),
        task_id=str(uuid4()),
        assignment_id=str(uuid4()),
        predecessor_submission_id=None,
        predecessor_submission_version=None,
        semantic_manifest_id=str(uuid4()),
        semantic_manifest_sha256=_sha("2"),
        guide_id=str(uuid4()),
        guide_version="1",
        source_snapshot_id=str(uuid4()),
        source_snapshot_sha256=_sha("3"),
        locked_guide_sha256=_sha("4"),
        effective_policy_id=str(uuid4()),
        locked_artifact_policy_sha256=_sha("5"),
        pre_submit_policy_id=str(uuid4()),
        locked_checker_policy_sha256=_sha("6"),
        effective_plan_sha256=_sha("7"),
        locked_policy_context_hash=_sha("8"),
    )
    attempt = SimpleNamespace(
        id=attempt_id,
        producer_request_type="submission_bundle",
        producer_ref=evidence.actor_profile_id,
        project_id=evidence.project_id,
        task_id=evidence.task_id,
        sha256=digest,
        byte_count=25,
        media_type="application/zip",
        replica_id=replica_id,
        receipt_id=None if observed_confirmation else str(uuid4()),
    )
    job = SimpleNamespace(
        id=job_id,
        originating_put_attempt_id=attempt_id,
        replica_id=replica_id,
        execution_generation=2,
    )
    intent = SimpleNamespace(id=str(uuid4()), pre_submit_evidence_set_id=evidence_id)
    replica = SimpleNamespace(
        id=replica_id,
        content_id=content_id,
        verification_state="verified",
        availability_state="available",
        integrity_state="valid",
    )
    content = SimpleNamespace(id=content_id, sha256=digest, byte_count=25)
    verification = SimpleNamespace(
        id=receipt_id,
        verification_job_id=job_id,
        execution_generation=2,
        outcome="verified",
        observed_sha256=digest,
        observed_byte_count=25,
    )
    put_receipt = SimpleNamespace(id=str(uuid4()) if observed_confirmation else attempt.receipt_id)
    now = datetime.now(UTC)
    session = SimpleNamespace(
        scalar=AsyncMock(
            side_effect=[
                job,
                attempt,
                intent,
                None,
                evidence,
                replica,
                verification,
                content,
                put_receipt,
                now,
            ]
        ),
        add=Mock(),
        flush=AsyncMock(),
    )

    admission = await SubmissionBundleAdmissionPublisher(session).publish_verified(
        verification_job_id=job_id,
        verification_receipt_id=receipt_id,
    )

    assert admission is not None
    assert admission.status == "ready"
    assert admission.pre_submit_evidence_set_id == evidence_id
    assert admission.artifact_content_id == content_id
    assert admission.put_operation_receipt_id == (
        None if observed_confirmation else attempt.receipt_id
    )
    assert admission.put_observation_receipt_id == (
        put_receipt.id if observed_confirmation else None
    )
    session.add.assert_called_once_with(admission)


@pytest.mark.asyncio
async def test_observed_confirmed_write_receipt_is_supported() -> None:
    attempt = SimpleNamespace(
        id=str(uuid4()),
        receipt_id=None,
        sha256=_sha("1"),
        byte_count=25,
    )
    observation = SimpleNamespace(id=str(uuid4()))
    session = SimpleNamespace(scalar=AsyncMock(return_value=observation))

    operation_id, observation_id = await SubmissionBundleAdmissionPublisher(
        session
    )._write_receipt_ids(attempt)

    assert operation_id is None
    assert observation_id == observation.id


@pytest.mark.asyncio
async def test_verified_guide_content_does_not_publish_submission_admission() -> None:
    job = SimpleNamespace(id=str(uuid4()), originating_put_attempt_id=str(uuid4()))
    attempt = SimpleNamespace(id=job.originating_put_attempt_id, producer_request_type="guide")
    session = SimpleNamespace(
        scalar=AsyncMock(side_effect=[job, attempt]),
        add=Mock(),
    )

    result = await SubmissionBundleAdmissionPublisher(session).publish_verified(
        verification_job_id=job.id,
        verification_receipt_id=str(uuid4()),
    )

    assert result is None
    session.add.assert_not_called()


@pytest.mark.asyncio
async def test_unverified_or_mismatched_lineage_is_not_publishable() -> None:
    digest = _sha("1")
    evidence = SimpleNamespace(
        id=str(uuid4()),
        terminal_status="failed",
        eligible=False,
        archive_sha256=digest,
        archive_byte_count=25,
        actor_profile_id=str(uuid4()),
        project_id=str(uuid4()),
        task_id=str(uuid4()),
    )
    attempt = SimpleNamespace(
        id=str(uuid4()),
        sha256=digest,
        byte_count=25,
        producer_ref=evidence.actor_profile_id,
        project_id=evidence.project_id,
        task_id=evidence.task_id,
        media_type="application/zip",
        replica_id=str(uuid4()),
    )
    job = SimpleNamespace(
        id=str(uuid4()),
        originating_put_attempt_id=attempt.id,
        replica_id=attempt.replica_id,
        execution_generation=1,
    )
    replica = SimpleNamespace(
        id=attempt.replica_id,
        content_id=str(uuid4()),
        verification_state="verified",
        availability_state="available",
        integrity_state="valid",
    )
    content = SimpleNamespace(id=replica.content_id, sha256=digest, byte_count=25)
    receipt = SimpleNamespace(
        verification_job_id=job.id,
        execution_generation=1,
        outcome="integrity_mismatch",
        observed_sha256=digest,
        observed_byte_count=25,
    )

    assert not SubmissionBundleAdmissionPublisher._matches_verified_lineage(
        evidence, attempt, job, replica, content, receipt
    )
    intent = SimpleNamespace(id=str(uuid4()), pre_submit_evidence_set_id=evidence.id)
    session = SimpleNamespace(
        scalar=AsyncMock(
            side_effect=[job, attempt, intent, None, evidence, replica, receipt, content]
        ),
        add=Mock(),
        flush=AsyncMock(),
    )
    attempt.producer_request_type = "submission_bundle"
    with pytest.raises(
        SubmissionBundleAdmissionPublicationError,
        match="verified submission bundle lineage does not match",
    ):
        await SubmissionBundleAdmissionPublisher(session).publish_verified(
            verification_job_id=job.id,
            verification_receipt_id=str(uuid4()),
        )
    session.add.assert_not_called()
    session.flush.assert_not_awaited()


@pytest.mark.asyncio
async def test_durable_put_admits_in_transaction_then_publishes(tmp_path) -> None:
    manager, prepared = await _prepared(tmp_path)
    evidence_set_id = uuid4()
    state = {"transaction": True}
    transaction = SimpleNamespace(is_active=True)
    session = SimpleNamespace(
        sync_session=SimpleNamespace(get_transaction=lambda: transaction),
        in_nested_transaction=lambda: False,
        in_transaction=lambda: state["transaction"],
        scalar=AsyncMock(return_value=None),
        begin=_transaction,
    )
    admission_result = ArtifactAdmissionResult(
        attempt_id=uuid4(),
        status="prepared",
        operation_identity=_sha("3"),
        request_digest=_sha("4"),
        charge_ids=(uuid4(),),
        replayed=False,
    )

    async def admit(request, **values):
        assert state["transaction"] is True
        assert type(request) is SubmissionBundleArtifactAdmissionRequest
        assert request.pre_submit_evidence_set_id == evidence_set_id
        assert request.custody.prepared_generation_id == prepared.generation_id
        assert type(request.custody.pass_capability) is PreSubmitPassCapability
        assert values["existing_transaction"] is True
        assert values["prepared_authorization"] is None
        assert values["submission_prepared_authorization"] is service._authorization
        return admission_result

    admission = SimpleNamespace(admit=admit)
    storage = SimpleNamespace(
        execute_committed_put=AsyncMock(return_value="object_confirmed"),
        resume_committed_put=AsyncMock(),
    )
    service = SubmissionBundleDurablePutService(
        session=session,
        admission=admission,
        storage=storage,
        authorization=object(),
    )
    try:
        retained, selected_evidence_id, durable = await service.admit_in_transaction(
            SubmissionBundleDurablePutRequest(
                prepared_authorization=None,
                prepared_artifact=prepared,
                pass_capability=_capability(prepared, evidence_set_id),
            )
        )
        storage.execute_committed_put.assert_not_awaited()
        state["transaction"] = False
        result = await service.publish_after_commit(
            retained,
            selected_evidence_id,
            durable,
        )
        assert result.pre_submit_evidence_set_id == evidence_set_id
        assert result.status == "object_confirmed"
        storage.execute_committed_put.assert_awaited_once()
        storage.resume_committed_put.assert_not_awaited()
        with pytest.raises(RuntimeError, match="prepared artifact is closed"):
            _ = prepared.generation_id
    finally:
        await prepared.close()
        manager.close()


def test_pass_capability_rejects_direct_construction() -> None:
    with pytest.raises(TypeError, match="can only be created by pre-submit evidence"):
        PreSubmitPassCapability(
            evidence_set_id=uuid4(),
            prepared_generation_id=uuid4(),
            predecessor_submission_id=None,
            effective_plan_sha256=_sha("7"),
            archive_sha256=_sha("1"),
            semantic_manifest_sha256=_sha("2"),
            storage_scheme="s3",
        )


def test_pass_capability_rejects_unregistered_service_owner() -> None:
    with pytest.raises(TypeError, match="can only be created by pre-submit evidence"):
        PreSubmitPassCapability._from_evidence_service(
            owner=object.__new__(PreSubmitEvidenceService),
            binding=object(),
            evidence_set_id=uuid4(),
            prepared_generation_id=uuid4(),
            predecessor_submission_id=None,
            effective_plan_sha256=_sha("7"),
            archive_sha256=_sha("1"),
            semantic_manifest_sha256=_sha("2"),
            storage_scheme="s3",
        )


def test_submission_custody_rejects_direct_construction() -> None:
    with pytest.raises(TypeError, match="requires live prepared work"):
        SubmissionBundlePreparedCustody()


def test_submission_request_rejects_evidence_without_live_custody() -> None:
    request = SubmissionBundleArtifactAdmissionRequest(
        pre_submit_evidence_set_id=uuid4(),
        custody=object(),
        replay_durable_intent_id=None,
    )
    with pytest.raises(TypeError, match="prepared custody is unavailable"):
        _ = request.source


def test_replay_lineage_includes_policy_catalogue_and_manifest_identity() -> None:
    values = {
        "actor_profile_id": str(uuid4()),
        "identity_link_id": str(uuid4()),
        "project_id": str(uuid4()),
        "task_id": str(uuid4()),
        "assignment_id": str(uuid4()),
        "predecessor_submission_id": None,
        "predecessor_submission_version": None,
        "archive_sha256": _sha("1"),
        "archive_byte_count": 10,
        "semantic_manifest_id": str(uuid4()),
        "semantic_manifest_sha256": _sha("2"),
        "guide_id": str(uuid4()),
        "guide_version": "1",
        "source_snapshot_id": str(uuid4()),
        "source_snapshot_sha256": _sha("3"),
        "locked_guide_sha256": _sha("4"),
        "effective_policy_id": str(uuid4()),
        "locked_artifact_policy_sha256": _sha("5"),
        "pre_submit_policy_id": str(uuid4()),
        "locked_checker_policy_sha256": _sha("6"),
        "effective_plan_sha256": _sha("7"),
        "catalogue_id": "workstream.default",
        "catalogue_version": "1",
        "catalogue_manifest_sha256": _sha("8"),
        "storage_scheme": "s3",
        "terminal_status": "passed",
        "eligible": True,
        "result_count": 2,
        "result_manifest_sha256": _sha("9"),
    }
    original = SimpleNamespace(**values)
    for field, changed in {
        "semantic_manifest_id": str(uuid4()),
        "locked_guide_sha256": _sha("a"),
        "effective_policy_id": str(uuid4()),
        "pre_submit_policy_id": str(uuid4()),
        "catalogue_id": "other.catalogue",
        "catalogue_version": "2",
        "catalogue_manifest_sha256": _sha("b"),
    }.items():
        drifted = SimpleNamespace(**{**values, field: changed})
        assert ArtifactAdmissionService._submission_replay_lineage(
            original
        ) != ArtifactAdmissionService._submission_replay_lineage(drifted)


@pytest.mark.asyncio
async def test_concurrent_pass_capability_consumption_has_one_winner(tmp_path) -> None:
    manager, prepared = await _prepared(tmp_path)
    capability = _capability(prepared, uuid4())

    def consume() -> bool:
        try:
            capability.consume(
                prepared_generation_id=prepared.generation_id,
                predecessor_submission_id=None,
                effective_plan_sha256=capability.effective_plan_sha256,
                archive_sha256=prepared.commitment.sha256,
                semantic_manifest_sha256=capability.semantic_manifest_sha256,
                storage_scheme=capability.storage_scheme,
            )
        except PreSubmitEvidenceConflict:
            return False
        return True

    try:
        outcomes = await asyncio.gather(
            asyncio.to_thread(consume),
            asyncio.to_thread(consume),
        )
        assert sorted(outcomes) == [False, True]
    finally:
        await prepared.close()
        manager.close()


@pytest.mark.asyncio
async def test_fresh_checked_custody_resumes_existing_committed_intent(tmp_path) -> None:
    manager, prepared = await _prepared(tmp_path)
    evidence_set_id = uuid4()
    replay_intent_id = uuid4()
    state = {"transaction": True}
    admission_result = ArtifactAdmissionResult(
        attempt_id=uuid4(),
        status="absent_replay_required",
        operation_identity=_sha("3"),
        request_digest=_sha("4"),
        charge_ids=(uuid4(),),
        replayed=True,
    )

    async def admit(request, **values):
        assert request.replay_durable_intent_id == replay_intent_id
        return admission_result

    storage = SimpleNamespace(
        execute_committed_put=AsyncMock(),
        resume_committed_put=AsyncMock(return_value="object_confirmed"),
    )
    service = SubmissionBundleDurablePutService(
        session=SimpleNamespace(
            sync_session=SimpleNamespace(get_transaction=lambda: SimpleNamespace(is_active=True)),
            in_nested_transaction=lambda: False,
            in_transaction=lambda: state["transaction"],
            scalar=AsyncMock(return_value=None),
            begin=_transaction,
        ),
        admission=SimpleNamespace(admit=admit),
        storage=storage,
        authorization=object(),
    )
    try:
        retained, selected_evidence_id, durable = await service.admit_in_transaction(
            SubmissionBundleDurablePutRequest(
                prepared_authorization=object.__new__(PreparedAuthorizationHandle),
                prepared_artifact=prepared,
                pass_capability=_capability(prepared, evidence_set_id),
                replay_durable_intent_id=replay_intent_id,
            )
        )
        state["transaction"] = False
        result = await service.publish_after_commit(
            retained,
            selected_evidence_id,
            durable,
        )
        assert result.replayed is True
        storage.resume_committed_put.assert_awaited_once()
        storage.execute_committed_put.assert_not_awaited()
    finally:
        await prepared.close()
        manager.close()


@pytest.mark.asyncio
async def test_object_confirmed_replay_does_not_reclaim_provider_work(tmp_path) -> None:
    manager, prepared = await _prepared(tmp_path)
    storage = SimpleNamespace(
        execute_committed_put=AsyncMock(),
        resume_committed_put=AsyncMock(),
    )
    service = SubmissionBundleDurablePutService(
        session=SimpleNamespace(
            in_transaction=lambda: False,
            scalar=AsyncMock(return_value=None),
            begin=_transaction,
        ),
        admission=SimpleNamespace(),
        storage=storage,
        authorization=object(),
    )
    try:
        result = await service.publish_after_commit(
            prepared,
            uuid4(),
            ArtifactAdmissionResult(
                attempt_id=uuid4(),
                status="object_confirmed",
                operation_identity=_sha("3"),
                request_digest=_sha("4"),
                charge_ids=(uuid4(),),
                replayed=True,
            ),
        )
        assert result.status == "object_confirmed"
        storage.execute_committed_put.assert_not_awaited()
        storage.resume_committed_put.assert_not_awaited()
    finally:
        await prepared.close()
        manager.close()


@pytest.mark.asyncio
async def test_durable_put_rejects_capability_replay_before_admission(tmp_path) -> None:
    manager, prepared = await _prepared(tmp_path)
    capability = _capability(prepared, uuid4())
    capability.consume(
        prepared_generation_id=prepared.generation_id,
        predecessor_submission_id=None,
        effective_plan_sha256=capability.effective_plan_sha256,
        archive_sha256=prepared.commitment.sha256,
        semantic_manifest_sha256=capability.semantic_manifest_sha256,
        storage_scheme=capability.storage_scheme,
    )
    admission = SimpleNamespace(admit=AsyncMock())
    service = SubmissionBundleDurablePutService(
        session=SimpleNamespace(
            sync_session=SimpleNamespace(get_transaction=lambda: SimpleNamespace(is_active=True)),
            in_nested_transaction=lambda: False,
            in_transaction=lambda: True,
        ),
        admission=admission,
        storage=SimpleNamespace(),
        authorization=object(),
    )
    try:
        with pytest.raises(PreSubmitEvidenceConflict):
            await service.admit_in_transaction(
                SubmissionBundleDurablePutRequest(
                    prepared_authorization=object.__new__(PreparedAuthorizationHandle),
                    prepared_artifact=prepared,
                    pass_capability=capability,
                )
            )
        admission.admit.assert_not_awaited()
    finally:
        await prepared.close()
        manager.close()


@pytest.mark.asyncio
async def test_deny_submission_authority_fails_closed() -> None:
    with pytest.raises(ArtifactAuthorityDeniedError):
        await DenySubmissionBundlePreparedAuthorization().consume(
            prepared_authorization=object.__new__(PreparedAuthorizationHandle),
            facts=object(),
        )
