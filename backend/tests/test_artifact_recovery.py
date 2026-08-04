"""PostgreSQL proofs for artifact recovery idempotency and retry lineage."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest  # type: ignore[import-not-found]
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import (  # type: ignore[import-not-found]
    async_sessionmaker,
    create_async_engine,
)

from app.adapters.artifacts.local import LocalStorageAdapter, LocalStorageBootstrap
from app.core.config import Settings
from app.core.hashing import canonical_json_hash
from app.interfaces.artifact_operations import ArtifactRecoveryRequest
from app.interfaces.artifacts import (
    ArtifactObjectMissingError,
    ArtifactStoreError,
    ArtifactStoreNamespaceClaim,
    ArtifactStoreUnavailableError,
)
from app.modules.artifacts.models import (
    ArtifactPutAttempt,
    ArtifactRecoveryAttempt,
    ArtifactVerificationJob,
)
from app.modules.artifacts.schemas import (
    ArtifactRecoveryAuthorizationEvidence,
    ArtifactRecoveryConflictError,
    ArtifactRecoveryIneligibleError,
    ArtifactAuthorityDeniedError,
    DenyArtifactRecoveryAuthority,
    GuideArtifactAdmissionRequest,
)
from app.modules.artifacts.service import (
    ArtifactAdmissionService,
    ArtifactRecoveryService,
    ArtifactStorageOrchestrator,
    artifact_storage_namespace_spec,
)
from app.modules.checkers.models import CheckerRun
from app.modules.actors.models import ActorIdentityLink, ActorProfile
from app.modules.authorization.runtime import (
    ActorKind,
    ActorStatus,
    HumanAuthorizationContext,
    IdentityLinkStatus,
)
from app.modules.authorization.prepared import PreparedAuthorizationHandle
from app.modules.authorization.catalogue import ActionId, PermissionId
from app.modules.projects.models import (
    GuideSourceSnapshot,
    GuideSourceSnapshotItem,
    ProjectGuide,
)
from project_create_fixtures import seed_historical_project, suspend_historical_product_custody
from app.modules.tasks.models import AuditEvent
from tests.artifact_store_helpers import artifact_admission_limit_settings, minted_source
from tests.test_artifact_admission import _admit_checker_output


class _AllowArtifactAuthority:
    async def prepare(self, **_values: object) -> None: ...

    async def consume(self, **_values: object) -> None: ...

    def discard(self) -> None: ...


class _AllowGuidePreparedAuthorization:
    def __init__(self, actor_profile_id: UUID) -> None:
        self.actor_profile_id = actor_profile_id
        self.handle = object.__new__(PreparedAuthorizationHandle)

    async def consume(self, *, prepared_authorization, facts) -> UUID:
        assert prepared_authorization is self.handle
        assert facts.byte_count >= 0
        return self.actor_profile_id


class _DenyTerminalArtifactAuthority(_AllowArtifactAuthority):
    phase: str | None = None

    async def prepare(self, **values: object) -> None:
        self.phase = str(values["phase"])

    async def consume(self, **_values: object) -> None:
        if self.phase == "terminal":
            raise ArtifactAuthorityDeniedError("terminal authority changed")

    def discard(self) -> None:
        self.phase = None


class _AllowRecoveryAuthority:
    async def authorize(self, **_values: object) -> ArtifactRecoveryAuthorizationEvidence:
        return ArtifactRecoveryAuthorizationEvidence(
            action_id=ActionId.ARTIFACT_VERIFICATION_JOB_RETRY,
            permission_id=PermissionId.ARTIFACT_VERIFICATION_JOB_RETRY.value,
            decision_id=uuid4(),
        )


class _AllowThenDenyRecoveryAuthority(_AllowRecoveryAuthority):
    def __init__(self) -> None:
        self.calls = 0

    async def authorize(self, **values: object) -> ArtifactRecoveryAuthorizationEvidence:
        self.calls += 1
        if self.calls == 2:
            raise ArtifactAuthorityDeniedError("terminal authority changed")
        return await super().authorize(**values)


@pytest.fixture
def recovery_database_env(isolated_database_env: str) -> str:
    """Use the runner-migrated schema and central transactional reset."""
    return isolated_database_env


def _settings(tmp_path: Path) -> Settings:
    root = tmp_path / "durable"
    root.mkdir(mode=0o700, parents=True)
    return Settings(
        **artifact_admission_limit_settings(1024),
        environment="test",
        artifact_store_backend="local",
        artifact_local_root=root,
        artifact_scratch_root=tmp_path / "scratch",
        artifact_scratch_minimum_free_bytes=0,
        artifact_provider_observation_maximum_attempts=1,
    )


def _context() -> HumanAuthorizationContext:
    return HumanAuthorizationContext(
        actor_profile_id=uuid4(),
        actor_kind=ActorKind.HUMAN,
        actor_status=ActorStatus.ACTIVE,
        identity_link_id=uuid4(),
        identity_link_status=IdentityLinkStatus.ACTIVE,
        request_id=uuid4(),
        correlation_id=uuid4(),
    )


async def _seed_recovery_actor(session, context: HumanAuthorizationContext) -> None:
    actor_id = str(context.actor_profile_id)
    session.add(
        ActorProfile(
            id=actor_id,
            actor_kind="human",
            status="active",
            provisioning_method="automatic_first_access",
            created_by="test",
        )
    )
    await session.flush()
    session.add(
        ActorIdentityLink(
            id=str(context.identity_link_id),
            actor_profile_id=actor_id,
            issuer="https://issuer.example.test",
            subject=f"human-{actor_id}",
            subject_kind="human",
            status="active",
            linked_by="test",
            last_verified_at=datetime.now(UTC),
        )
    )


async def _seed_guide_owner(session, context: HumanAuthorizationContext) -> str:
    await _seed_recovery_actor(session, context)
    project_id = str(uuid4())
    await seed_historical_project(
        session,
        project_id=project_id,
        name="Guide recovery project",
        slug=f"guide-recovery-{project_id}",
    )
    await session.flush()
    return project_id


async def _exhausted_guide_job(session, settings, tmp_path, context):
    namespace = artifact_storage_namespace_spec(
        settings,
        LocalStorageBootstrap(LocalStorageAdapter(root=settings.artifact_local_root)),
    )
    bootstrap = LocalStorageBootstrap(LocalStorageAdapter(root=settings.artifact_local_root))
    store = bootstrap.initialize_after_namespace_claim(
        ArtifactStoreNamespaceClaim(
            adapter_identity=bootstrap.identity,
            namespace_identity=bootstrap.namespace_identity,
            namespace_fingerprint=namespace.namespace_fingerprint,
        )
    )
    source_cm = minted_source(tmp_path / "guide-source", b"recover guide")
    source = await source_cm.__aenter__()
    project_id = await _seed_guide_owner(session, context)
    guide_id, snapshot_id, item_id = (str(uuid4()) for _ in range(3))
    async with suspend_historical_product_custody(
        session,
        table="project_guides",
        triggers=("guide_mutation_product_custody",),
    ):
        session.add(
            ProjectGuide(
                id=guide_id,
                project_id=project_id,
                version="v1",
                status="draft",
                content_markdown="# Guide",
                created_by="test",
            )
        )
        await session.flush()
    async with suspend_historical_product_custody(
        session,
        table="guide_source_snapshots",
        triggers=("source_snapshot_product_custody",),
    ):
        session.add(
            GuideSourceSnapshot(
                id=snapshot_id,
                project_id=project_id,
                guide_id=guide_id,
                guide_version="v1",
                manifest_schema_version="v1",
                manifest_json={"items": [item_id]},
                bundle_hash=canonical_json_hash({"items": [item_id]}),
                captured_by=str(context.actor_profile_id),
            )
        )
        await session.flush()
    async with suspend_historical_product_custody(
        session,
        table="guide_source_snapshot_items",
        triggers=("guide_source_snapshot_items_custody",),
    ):
        session.add(
            GuideSourceSnapshotItem(
                id=item_id,
                source_snapshot_id=snapshot_id,
                item_order=0,
                source_kind="inline",
                source_label="guide.md",
                ingestion_adapter="inline",
                media_type=source.commitment.media_type,
            )
        )
        await session.flush()
    await session.commit()
    prepared = _AllowGuidePreparedAuthorization(context.actor_profile_id)
    admission = await ArtifactAdmissionService(session, settings, namespace).admit(
        GuideArtifactAdmissionRequest(
            guide_source_item_id=UUID(item_id),
            source=source,
            operation_identity=canonical_json_hash(
                {"request_type": "guide", "guide_source_item_id": item_id}
            ),
            request_digest="sha256:" + "a" * 64,
        ),
        guide_prepared_authorization=prepared,  # type: ignore[arg-type]
        prepared_authorization=prepared.handle,
    )
    orchestrator = ArtifactStorageOrchestrator(
        session, store, namespace, settings, _AllowArtifactAuthority()
    )
    await orchestrator.execute_committed_put(attempt_id=admission.attempt_id, source=source)
    job = await session.scalar(
        select(ArtifactVerificationJob).where(
            ArtifactVerificationJob.originating_put_attempt_id == str(admission.attempt_id)
        )
    )
    if job is None:
        attempt = await session.get(ArtifactPutAttempt, str(admission.attempt_id))
        assert attempt is not None and attempt.replica_id is not None
        job = ArtifactVerificationJob(
            id=str(uuid4()),
            originating_put_attempt_id=attempt.id,
            replica_id=attempt.replica_id,
            status="pending",
            maximum_attempts=1,
        )
        session.add(job)
        await session.commit()
    job_id = job.id
    await session.rollback()
    orchestrator._read_complete = AsyncMock(side_effect=ArtifactStoreUnavailableError("down"))
    await orchestrator.verify_object(UUID(job_id))
    job = await session.get(ArtifactVerificationJob, job_id)
    assert job is not None
    await session.refresh(job)
    await session.commit()
    await source_cm.__aexit__(None, None, None)
    return project_id, job, orchestrator, bootstrap


async def _exhausted_job(session, settings, tmp_path, context):
    await _seed_recovery_actor(session, context)
    namespace = artifact_storage_namespace_spec(
        settings,
        LocalStorageBootstrap(LocalStorageAdapter(root=settings.artifact_local_root)),
    )
    bootstrap = LocalStorageBootstrap(LocalStorageAdapter(root=settings.artifact_local_root))
    store = bootstrap.initialize_after_namespace_claim(
        ArtifactStoreNamespaceClaim(
            adapter_identity=bootstrap.identity,
            namespace_identity=bootstrap.namespace_identity,
            namespace_fingerprint=namespace.namespace_fingerprint,
        )
    )
    async with minted_source(tmp_path / "checker-output", b"recover checker output") as source:
        project_id, task_id, checker_run_id, admission = await _admit_checker_output(
            session, settings, namespace, source
        )
        orchestrator = ArtifactStorageOrchestrator(
            session, store, namespace, settings, _AllowArtifactAuthority()
        )
        await orchestrator.execute_committed_put(attempt_id=admission.attempt_id, source=source)
        job = await session.scalar(
            select(ArtifactVerificationJob).where(
                ArtifactVerificationJob.originating_put_attempt_id == str(admission.attempt_id)
            )
        )
        assert job is not None
        job_id = job.id
        await session.rollback()
        orchestrator._read_complete = AsyncMock(side_effect=ArtifactStoreUnavailableError("down"))
        await orchestrator.verify_object(UUID(job_id))
        job = await session.get(ArtifactVerificationJob, job_id)
        assert job is not None
        checker_run = await session.get(CheckerRun, checker_run_id)
        assert checker_run is not None
        job.recovery_submission_id = checker_run.submission_id
        await session.refresh(job)
        await session.commit()
    return project_id, task_id, job, orchestrator, bootstrap


def _request(
    context: HumanAuthorizationContext,
    project_id: str,
    task_id: str | None,
    job: ArtifactVerificationJob,
    *,
    reason: str = "provider remained unavailable",
    client_idempotency_key: str = "recovery-1",
) -> ArtifactRecoveryRequest:
    return ArtifactRecoveryRequest(
        authorization_context=context,
        project_id=UUID(project_id),
        task_id=UUID(task_id) if task_id is not None else None,
        submission_id=(
            UUID(job.recovery_submission_id)
            if getattr(job, "recovery_submission_id", None) is not None
            else None
        ),
        source_verification_job_id=UUID(job.id),
        reason=reason,
        client_idempotency_key=client_idempotency_key,
        expected_source_job_cas_version=job.cas_version,
    )


@pytest.mark.asyncio
async def test_exact_replay_creates_one_recovery_job_and_audit(
    recovery_database_env: str, tmp_path: Path
) -> None:
    engine = create_async_engine(recovery_database_env)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            context = _context()
            settings = _settings(tmp_path)
            project_id, task_id, source, _orchestrator, bootstrap = await _exhausted_job(
                session, settings, tmp_path, context
            )
            service = ArtifactRecoveryService(session, settings, _AllowRecoveryAuthority())
            request = _request(context, project_id, task_id, source)
            first = await service.create(request)
            replay = await service.create(request)
            assert first.retry_verification_job_id == replay.retry_verification_job_id
            assert replay.replayed is True
            assert await session.scalar(select(func.count(ArtifactRecoveryAttempt.id))) == 1
            assert await session.scalar(select(func.count(ArtifactVerificationJob.id))) == 2
            assert (
                await session.scalar(
                    select(func.count(AuditEvent.id)).where(
                        AuditEvent.event_type == "ArtifactRecoveryInitiated"
                    )
                )
                == 1
            )
            bootstrap.close()
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_taskless_recovery_and_deny_only_authority_boundary(
    recovery_database_env: str, tmp_path: Path
) -> None:
    engine = create_async_engine(recovery_database_env)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            context = _context()
            settings = _settings(tmp_path)
            project_id, source, _orchestrator, bootstrap = await _exhausted_guide_job(
                session, settings, tmp_path, context
            )
            request = _request(context, project_id, None, source)
            with pytest.raises(ArtifactAuthorityDeniedError):
                await ArtifactRecoveryService(
                    session, settings, DenyArtifactRecoveryAuthority()
                ).create(request)
            assert await session.scalar(select(func.count(ArtifactRecoveryAttempt.id))) == 0
            assert await session.scalar(select(func.count(ArtifactVerificationJob.id))) == 1
            await session.rollback()
            created = await ArtifactRecoveryService(
                session, settings, _AllowRecoveryAuthority()
            ).create(request)
            with pytest.raises(ArtifactAuthorityDeniedError):
                await ArtifactRecoveryService(
                    session, settings, DenyArtifactRecoveryAuthority()
                ).create(request)
            assert await session.scalar(select(func.count(ArtifactRecoveryAttempt.id))) == 1
            assert await session.scalar(select(func.count(ArtifactVerificationJob.id))) == 2
            assert (
                await session.scalar(
                    select(func.count(AuditEvent.id)).where(
                        AuditEvent.event_type == "ArtifactRecoveryInitiated"
                    )
                )
                == 1
            )
            await session.rollback()
            replay = await ArtifactRecoveryService(
                session, settings, _AllowRecoveryAuthority()
            ).create(request)
            assert replay.replayed is True
            assert created.retry_verification_job_id == replay.retry_verification_job_id
            bootstrap.close()
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_changed_or_ineligible_recovery_has_no_side_effects(
    recovery_database_env: str, tmp_path: Path
) -> None:
    engine = create_async_engine(recovery_database_env)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            context = _context()
            settings = _settings(tmp_path)
            project_id, task_id, source, _orchestrator, bootstrap = await _exhausted_job(
                session, settings, tmp_path, context
            )
            service = ArtifactRecoveryService(session, settings, _AllowRecoveryAuthority())
            created = await service.create(_request(context, project_id, task_id, source))
            with pytest.raises(ArtifactRecoveryConflictError):
                await service.create(
                    _request(
                        context,
                        project_id,
                        task_id,
                        source,
                        reason="changed",
                    )
                )
            source.status = "verified"
            source.terminal_result_code = "verified"
            await session.commit()
            with pytest.raises(ArtifactRecoveryConflictError):
                await service.create(
                    _request(
                        context,
                        project_id,
                        task_id,
                        source,
                        client_idempotency_key="different",
                    )
                )
            assert await session.scalar(select(func.count(ArtifactRecoveryAttempt.id))) == 1

            retry = await session.get(
                ArtifactVerificationJob, str(created.retry_verification_job_id)
            )
            assert retry is not None
            retry.recovery_submission_id = source.recovery_submission_id
            retry_request = _request(
                context,
                project_id,
                task_id,
                retry,
                client_idempotency_key="retry-pending",
            )
            await session.rollback()
            with pytest.raises(ArtifactRecoveryIneligibleError):
                await service.create(retry_request)
            bootstrap.close()
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_terminal_recovery_authority_change_rolls_back_all_facts(
    recovery_database_env: str, tmp_path: Path
) -> None:
    engine = create_async_engine(recovery_database_env)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            context = _context()
            settings = _settings(tmp_path)
            project_id, task_id, source, _orchestrator, bootstrap = await _exhausted_job(
                session, settings, tmp_path, context
            )
            authority = _AllowThenDenyRecoveryAuthority()
            with pytest.raises(ArtifactAuthorityDeniedError):
                await ArtifactRecoveryService(session, settings, authority).create(
                    _request(context, project_id, task_id, source)
                )
            assert authority.calls == 2
            assert await session.scalar(select(func.count(ArtifactRecoveryAttempt.id))) == 0
            assert await session.scalar(select(func.count(ArtifactVerificationJob.id))) == 1
            assert (
                await session.scalar(
                    select(func.count(AuditEvent.id)).where(
                        AuditEvent.event_type == "ArtifactRecoveryInitiated"
                    )
                )
                == 0
            )
            bootstrap.close()
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_retry_terminalizes_recovery_under_verification_fence(
    recovery_database_env: str, tmp_path: Path
) -> None:
    engine = create_async_engine(recovery_database_env)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            context = _context()
            settings = _settings(tmp_path)
            project_id, task_id, source, orchestrator, bootstrap = await _exhausted_job(
                session, settings, tmp_path, context
            )
            created = await ArtifactRecoveryService(
                session, settings, _AllowRecoveryAuthority()
            ).create(_request(context, project_id, task_id, source))
            orchestrator._read_complete = ArtifactStorageOrchestrator._read_complete.__get__(
                orchestrator
            )
            assert await orchestrator.verify_object(created.retry_verification_job_id) == "verified"
            recovery = await session.get(ArtifactRecoveryAttempt, str(created.recovery_attempt_id))
            assert recovery is not None
            assert recovery.status == "succeeded"
            assert recovery.terminal_result_code == "verified"
            assert recovery.terminal_audit_event_id is not None
            assert (
                await session.scalar(
                    select(func.count(AuditEvent.id)).where(
                        AuditEvent.event_type == "ArtifactRecoveryCompleted"
                    )
                )
                == 1
            )
            bootstrap.close()
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_terminal_authority_drift_writes_no_recovery_terminal_facts(
    recovery_database_env: str, tmp_path: Path
) -> None:
    engine = create_async_engine(recovery_database_env)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            context = _context()
            settings = _settings(tmp_path)
            project_id, task_id, source, orchestrator, bootstrap = await _exhausted_job(
                session, settings, tmp_path, context
            )
            created = await ArtifactRecoveryService(
                session, settings, _AllowRecoveryAuthority()
            ).create(_request(context, project_id, task_id, source))
            orchestrator._authority = _DenyTerminalArtifactAuthority()
            orchestrator._read_complete = ArtifactStorageOrchestrator._read_complete.__get__(
                orchestrator
            )
            with pytest.raises(ArtifactAuthorityDeniedError):
                await orchestrator.verify_object(created.retry_verification_job_id)
            recovery = await session.get(ArtifactRecoveryAttempt, str(created.recovery_attempt_id))
            retry = await session.get(
                ArtifactVerificationJob, str(created.retry_verification_job_id)
            )
            assert recovery is not None and retry is not None
            assert recovery.status == "requested"
            assert recovery.terminal_at is None
            assert retry.status == "running"
            assert retry.terminal_at is None
            assert (
                await session.scalar(
                    select(func.count(AuditEvent.id)).where(
                        AuditEvent.event_type == "ArtifactRecoveryCompleted"
                    )
                )
                == 0
            )
            bootstrap.close()
    finally:
        await engine.dispose()


@pytest.mark.parametrize(
    ("provider_result", "expected_outcome"),
    [
        (ArtifactObjectMissingError("missing"), "missing"),
        (("sha256:" + "0" * 64, 1), "integrity_mismatch"),
        (ArtifactStoreError("provider conflict"), "conflict"),
    ],
)
@pytest.mark.asyncio
async def test_every_failed_retry_outcome_terminalizes_recovery_once(
    recovery_database_env: str,
    tmp_path: Path,
    provider_result: object,
    expected_outcome: str,
) -> None:
    engine = create_async_engine(recovery_database_env)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            context = _context()
            settings = _settings(tmp_path)
            project_id, task_id, source, orchestrator, bootstrap = await _exhausted_job(
                session, settings, tmp_path, context
            )
            created = await ArtifactRecoveryService(
                session, settings, _AllowRecoveryAuthority()
            ).create(_request(context, project_id, task_id, source))
            if isinstance(provider_result, Exception):
                orchestrator._read_complete = AsyncMock(side_effect=provider_result)
            else:
                orchestrator._read_complete = AsyncMock(return_value=provider_result)
            assert (
                await orchestrator.verify_object(created.retry_verification_job_id)
                == expected_outcome
            )
            recovery = await session.get(ArtifactRecoveryAttempt, str(created.recovery_attempt_id))
            assert recovery is not None
            assert (recovery.status, recovery.terminal_result_code) == (
                "failed",
                expected_outcome,
            )
            assert (
                await session.scalar(
                    select(func.count(AuditEvent.id)).where(
                        AuditEvent.event_type == "ArtifactRecoveryCompleted"
                    )
                )
                == 1
            )
            bootstrap.close()
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_concurrent_exact_replay_has_one_envelope_and_retry_job(
    recovery_database_env: str, tmp_path: Path
) -> None:
    engine = create_async_engine(recovery_database_env)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    bootstrap = None
    try:
        async with factory() as setup:
            context = _context()
            settings = _settings(tmp_path)
            project_id, task_id, source, _orchestrator, bootstrap = await _exhausted_job(
                setup, settings, tmp_path, context
            )
            request = _request(context, project_id, task_id, source)
        async with factory() as first_session, factory() as second_session:
            first, second = await asyncio.gather(
                ArtifactRecoveryService(first_session, settings, _AllowRecoveryAuthority()).create(
                    request
                ),
                ArtifactRecoveryService(second_session, settings, _AllowRecoveryAuthority()).create(
                    request
                ),
            )
            assert {first.replayed, second.replayed} == {False, True}
            assert first.retry_verification_job_id == second.retry_verification_job_id
        async with factory() as proof:
            assert await proof.scalar(select(func.count(ArtifactRecoveryAttempt.id))) == 1
            assert await proof.scalar(select(func.count(ArtifactVerificationJob.id))) == 2
    finally:
        if bootstrap is not None:
            bootstrap.close()
        await engine.dispose()


@pytest.mark.asyncio
async def test_exhausted_retry_can_form_only_the_next_linear_chain_link(
    recovery_database_env: str, tmp_path: Path
) -> None:
    engine = create_async_engine(recovery_database_env)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            context = _context()
            settings = _settings(tmp_path)
            project_id, task_id, source, orchestrator, bootstrap = await _exhausted_job(
                session, settings, tmp_path, context
            )
            service = ArtifactRecoveryService(session, settings, _AllowRecoveryAuthority())
            first = await service.create(_request(context, project_id, task_id, source))
            orchestrator._read_complete = AsyncMock(
                side_effect=ArtifactStoreUnavailableError("still unavailable")
            )
            assert (
                await orchestrator.verify_object(first.retry_verification_job_id)
                == "provider_unavailable"
            )
            retry = await session.get(ArtifactVerificationJob, str(first.retry_verification_job_id))
            first_attempt = await session.get(
                ArtifactRecoveryAttempt, str(first.recovery_attempt_id)
            )
            assert retry is not None and first_attempt is not None
            retry.recovery_submission_id = source.recovery_submission_id
            assert first_attempt.status == "failed"
            assert first_attempt.terminal_result_code == "provider_unavailable"
            second_request = _request(
                context,
                project_id,
                task_id,
                retry,
                client_idempotency_key="recovery-2",
            )
            first_attempt_id = first_attempt.id
            await session.rollback()
            second = await service.create(second_request)
            second_attempt = await session.get(
                ArtifactRecoveryAttempt, str(second.recovery_attempt_id)
            )
            assert second_attempt is not None
            assert second_attempt.parent_recovery_attempt_id == first_attempt_id
            assert second.source_verification_job_id == first.retry_verification_job_id
            bootstrap.close()
    finally:
        await engine.dispose()
