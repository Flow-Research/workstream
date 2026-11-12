"""Real AUTH/TASK/PROJECT T1 transaction and exact replay proof."""
import asyncio
from datetime import timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.adapters.tasks import task_submission_context_port
from app.core.identifiers import new_record_id
from app.modules.artifacts.api.submission_intake import SubmissionIntakeMetadata, SubmissionSourceCapacityLimits, SubmissionSourceUpload
from app.modules.artifacts.intake.models import SubmissionIntakeOperation
from app.modules.artifacts.intake.repository import IntakeCustodyConflict
from app.modules.tasks.api.submission_context import TaskSubmissionContextUnavailable
from app.modules.tasks.intake_custody import IntakeTaskCustody
from tests.artifacts.test_submission_intake_custody import repository, record_eof
from tests.selected_policy_fixtures import approved_selected_policy_fixture
from tests.tasks.lineage_fixtures import seed_started_task_for_artifact_test
from tests.test_artifact_admission import _namespace, _settings
# Signed grant fixtures are scoped to this integration suite.
from tests.authentication.fixtures import (
    auth_database_env as auth_database_env,
    clear_settings_cache as clear_settings_cache,
    rsa_signing_material as rsa_signing_material,
)
from tests.authorization.admin_access.fixtures import (
    signed_access as signed_access,
    admin_access as admin_access,
)


@pytest.fixture
async def admission_intake(tmp_path, isolated_database_env, admin_access, request):
    from app.adapters.projects import project_locked_policy_context_port
    from app.modules.artifacts.intake.foreground_admission import ForegroundIntakeAdmission
    from app.modules.authorization.submission_intake import SubmissionIntakeAuthorization
    from tests.authorization.task_authority.test_postgresql import context, grant, project_manager

    engine = create_async_engine(isolated_database_env)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    namespace = _namespace(_settings(tmp_path))
    if getattr(request, "param", None) == "aws":
        from app.interfaces.artifacts import ArtifactStoreNamespaceIdentity, artifact_store_namespace_material
        from app.interfaces.external_services import ExternalServiceAdapterIdentity
        from app.modules.artifacts.service import ArtifactStorageNamespaceSpec
        identity = ArtifactStoreNamespaceIdentity("aws-s3-v1", (
            ("addressing_style", "virtual"), ("bucket", "intake-refusal-fixture"),
            ("private_prefix", "workstream/artifacts"), ("region", "us-east-1"),
        ))
        descriptor, fingerprint = artifact_store_namespace_material(
            backend="s3", adapter_identity=ExternalServiceAdapterIdentity("artifact_store", "s3"),
            namespace_identity=identity,
        )
        namespace = ArtifactStorageNamespaceSpec("s3", "s3", identity.provider_profile, descriptor, fingerprint)
    try:
        from tests.checkers.external.support import pre_registry_spec, post_registry_spec
        plan, _ = await approved_selected_policy_fixture(
            factory, namespace, guide_version="v1",
            pre_submit_registry_spec=None if getattr(request, "param", None) == "no_pre" else pre_registry_spec(),
            post_submit_registry_spec=None if getattr(request, "param", None) == "no_post" else post_registry_spec(),
        )
        project = plan.lineage.project_id
        manager = await project_manager(admin_access, project)
        grant_id = await grant(admin_access, manager, project)
        actor = await context(admin_access)
        task, assignment = new_record_id(), new_record_id()
        async with engine.begin() as connection:
            await seed_started_task_for_artifact_test(connection, dict(
                task=str(task), assignment=str(assignment), project=str(project), actor=str(actor.actor_profile_id),
            ))
        admission = ForegroundIntakeAdmission(
            factory, tasks=lambda session: IntakeTaskCustody(session, task_submission_context_port(session)),
            task_contexts=task_submission_context_port, projects=project_locked_policy_context_port,
            authorization=lambda session: SubmissionIntakeAuthorization(session, actor), namespace=namespace,
            capacity_limits=SubmissionSourceCapacityLimits(maximum_total_bytes=1_000_000), maximum_raw_bytes=1024,
            upload_duration=timedelta(seconds=300), lease_duration=timedelta(seconds=60),
        )
        yield SimpleNamespace(factory=factory, actor=actor, task=task, assignment=assignment,
                              admission=admission, project=project, namespace=namespace,
                              access=admin_access, manager=manager, grant_id=grant_id)
    finally:
        await engine.dispose()


async def admit_new(fixture, *, key=None, metadata=None):
    return await fixture.admission.admit(
        metadata or SubmissionIntakeMetadata(task_id=fixture.task, assignment_id=fixture.assignment),
        actor_id=fixture.actor.actor_profile_id, identity_link_id=fixture.actor.identity_link_id,
        idempotency_key=key or new_record_id(), declared_raw_bytes=None,
    )


async def test_t1_commits_exact_owner_charge_pointer_and_allow(admission_intake):
    from sqlalchemy import select
    from app.modules.artifacts.intake.foreground_admission import IntakeReservationOwner, IntakeReplay
    from app.modules.artifacts.intake.models import SubmissionSourceCharge
    from app.modules.tasks.models import AuditEvent, WorkstreamTask

    f = admission_intake
    key = new_record_id()
    owner = await admit_new(f, key=key)
    assert isinstance(owner, IntakeReservationOwner)
    async with f.factory() as session:
        row = await session.get(SubmissionIntakeOperation, str(owner.operation_id))
        charge = await session.get(SubmissionSourceCharge, row.id)
        task = await session.get(WorkstreamTask, str(f.task))
        assert row.state == "receiving" and row.raw_sha256 is None
        assert row.idempotency_key == str(key) and row.identity_link_id == str(f.actor.identity_link_id)
        assert task.active_submission_operation_id == row.id
        assert charge.accounted_bytes == 1024 and charge.state == "reserved"
        events = list(await session.scalars(select(AuditEvent).where(
            AuditEvent.action_id == "submission.intake.reserve", AuditEvent.resource_id == row.id)))
        assert len(events) == 1 and events[0].after_facts["allowed"] is True
    retry = await admit_new(f, key=key)
    assert isinstance(retry, IntakeReplay) and retry.operation_id == owner.operation_id

    async def forbidden_body():
        pytest.fail("a retry without EOF read the body")
        yield b"never"

    with pytest.raises(IntakeCustodyConflict, match="submission_operation_in_progress"):
        await f.admission.replay(
            SubmissionIntakeMetadata(task_id=f.task, assignment_id=f.assignment), forbidden_body(),
            actor_id=f.actor.actor_profile_id, idempotency_key=key, declared_raw_bytes=None,
            idle_timeout_seconds=1, replay_duration=timedelta(seconds=10),
        )


async def test_t1_replays_eof_before_provider_completion_without_changing_custody(admission_intake):
    from app.modules.artifacts.intake.foreground_admission import IntakeReplay
    f = admission_intake
    key = new_record_id()
    owner = await admit_new(f, key=key)
    payload = b"original raw ZIP"
    await record_intake_eof(f, owner, payload)

    async def body(value):
        yield value

    arguments = dict(actor_id=f.actor.actor_profile_id, idempotency_key=key,
                     declared_raw_bytes=None, idle_timeout_seconds=1, replay_duration=timedelta(seconds=10))
    metadata = SubmissionIntakeMetadata(task_id=f.task, assignment_id=f.assignment)
    replay = await f.admission.replay(metadata, body(payload), **arguments)
    assert isinstance(replay, IntakeReplay) and replay.operation_id == owner.operation_id
    with pytest.raises(IntakeCustodyConflict, match="submission_idempotency_conflict"):
        await f.admission.replay(metadata, body(b"different"), **arguments)
    async with f.factory() as session:
        row = await session.get(SubmissionIntakeOperation, str(owner.operation_id))
        assert row.state == "receiving" and row.provider_generation is None
        assert (row.lease_id, row.lease_generation) == (str(owner.lease_id), owner.generation)



    async with f.factory.begin() as session:
        await repository(session).terminalize(owner.operation_id, owner.lease_id, owner.generation,
                                              state="failed", failure_code="upload_failed")
    replacement = await admit_new(f)
    terminal = await f.admission.replay(metadata, body(payload), **arguments)
    assert terminal.operation_id == owner.operation_id and terminal.state == "failed"
    assert terminal.failure_code == "upload_failed" and replacement.operation_id != owner.operation_id


async def test_t1_same_key_race_has_one_owner_and_one_operation(admission_intake):
    from sqlalchemy import select, func
    from app.modules.artifacts.intake.foreground_admission import IntakeReservationOwner, IntakeReplay
    f = admission_intake
    key = new_record_id()
    results = await asyncio.wait_for(asyncio.gather(admit_new(f, key=key), admit_new(f, key=key)), 10)
    assert sum(isinstance(value, IntakeReservationOwner) for value in results) == 1
    assert sum(isinstance(value, IntakeReplay) for value in results) == 1
    assert results[0].operation_id == results[1].operation_id
    async with f.factory() as session:
        assert await session.scalar(select(func.count()).select_from(SubmissionIntakeOperation)) == 1


async def test_t1_lost_commit_ack_resolves_as_replay_not_upload_owner(admission_intake):
    from sqlalchemy.ext.asyncio import AsyncSession
    from app.modules.artifacts.intake.foreground_admission import IntakeReplay
    f = admission_intake
    committed = False

    class LostAcknowledgement(AsyncSession):
        async def commit(self):
            nonlocal committed
            await super().commit()
            if not committed:
                committed = True
                raise OSError("simulated lost commit acknowledgement")

    f.admission._sessions = async_sessionmaker(f.factory.kw["bind"], class_=LostAcknowledgement, expire_on_commit=False)
    result = await admit_new(f)
    assert committed and isinstance(result, IntakeReplay) and result.state == "receiving"
    async with f.factory() as session:
        assert await session.get(SubmissionIntakeOperation, str(result.operation_id)) is not None


async def test_t1_revoked_grant_blocks_new_admission_and_existing_replay(admission_intake):
    from sqlalchemy import func, select
    from app.modules.authorization.api.submission_intake import IntakeAuthorityDenied
    f = admission_intake
    key = new_record_id()
    owner = await admit_new(f, key=key)
    response = await f.access.signed.client.post(
        f"/api/v1/projects/{f.project}/role-grants/{f.grant_id}/revoke",
        headers=f.manager.headers | {"Idempotency-Key": str(new_record_id())},
        json={"reason": "Withdraw intake test grant"},
    )
    assert response.status_code == 200, response.text
    for retry_key in (key, new_record_id()):
        with pytest.raises(IntakeAuthorityDenied):
            await admit_new(f, key=retry_key)
    async with f.factory() as session:
        assert await session.scalar(select(func.count()).select_from(SubmissionIntakeOperation)) == 1
        row = await session.get(SubmissionIntakeOperation, str(owner.operation_id))
        assert row.state == "receiving" and row.lease_id == str(owner.lease_id)


async def test_t1_namespace_refusal_leaves_no_pointer_charge_or_allow(admission_intake):
    from dataclasses import replace
    from sqlalchemy import func, select
    from app.modules.artifacts.intake.models import SubmissionSourceCharge
    from app.modules.tasks.models import AuditEvent, WorkstreamTask
    f = admission_intake
    f.admission._namespace = replace(f.namespace, namespace_fingerprint="sha256:" + "0" * 64)
    with pytest.raises(IntakeCustodyConflict, match="intake_namespace_unavailable"):
        await admit_new(f)
    async with f.factory() as session:
        assert await session.scalar(select(func.count()).select_from(SubmissionIntakeOperation)) == 0
        assert await session.scalar(select(func.count()).select_from(SubmissionSourceCharge)) == 0
        task = await session.get(WorkstreamTask, str(f.task))
        assert task.active_submission_operation_id is None
        assert not list(await session.scalars(select(AuditEvent).where(
            AuditEvent.action_id == "submission.intake.reserve")))


async def test_t1_different_key_and_changed_metadata_cannot_replace_active_owner(admission_intake):
    f = admission_intake
    key = new_record_id()
    owner = await admit_new(f, key=key)
    with pytest.raises(TaskSubmissionContextUnavailable, match="task_submission_operation_in_progress"):
        await admit_new(f)
    with pytest.raises(IntakeCustodyConflict, match="submission_idempotency_conflict"):
        await admit_new(f, key=key, metadata=SubmissionIntakeMetadata(task_id=f.task, assignment_id=new_record_id()))
    async with f.factory() as session:
        row = await session.get(SubmissionIntakeOperation, str(owner.operation_id))
        assert row.state == "receiving" and row.assignment_id == str(f.assignment)


async def test_t1_capacity_refusal_rolls_back_pointer_operation_and_allow(admission_intake):
    from sqlalchemy import select, func
    from app.modules.artifacts.intake.capacity import SubmissionSourceCapacityConflict
    from app.modules.tasks.models import AuditEvent, WorkstreamTask
    f = admission_intake
    f.admission._capacity = SubmissionSourceCapacityLimits(maximum_total_bytes=1)
    with pytest.raises(SubmissionSourceCapacityConflict, match="source_capacity_exhausted"):
        await admit_new(f)
    async with f.factory() as session:
        assert await session.scalar(select(func.count()).select_from(SubmissionIntakeOperation)) == 0
        assert (await session.get(WorkstreamTask, str(f.task))).active_submission_operation_id is None
        assert not list(await session.scalars(select(AuditEvent).where(
            AuditEvent.action_id == "submission.intake.reserve")))


async def test_t1_cancelled_commit_drains_and_never_returns_upload_owner(admission_intake):
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import AsyncSession
    from app.modules.artifacts.intake.models import SubmissionSourceCharge
    f = admission_intake
    committed, release = asyncio.Event(), asyncio.Event()
    key = new_record_id()

    class DelayedAcknowledgement(AsyncSession):
        async def commit(self):
            await super().commit()
            committed.set()
            await release.wait()

    f.admission._sessions = async_sessionmaker(f.factory.kw["bind"], class_=DelayedAcknowledgement, expire_on_commit=False)
    command = asyncio.create_task(admit_new(f, key=key))
    try:
        await asyncio.wait_for(committed.wait(), 10)
        command.cancel()
        await asyncio.sleep(0)
        command.cancel()
        assert not command.done()
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(command, 10)
    finally:
        release.set()
        command.cancel()
        await asyncio.gather(command, return_exceptions=True)
    async with f.factory() as session:
        row = await session.scalar(select(SubmissionIntakeOperation).where(
            SubmissionIntakeOperation.idempotency_key == str(key)))
        assert row is not None and row.state == "receiving"
        assert (await session.get(SubmissionSourceCharge, row.id)).accounted_bytes == 1024


async def record_intake_eof(f, owner, payload):
    import hashlib
    async with f.factory.begin() as session:
        repo = repository(session)
        intent = await repo.prepare_upload(owner.operation_id, owner.lease_id, owner.generation,
                                          part_bytes=5 * 1024 * 1024, idle_timeout_seconds=1)
        await repo.record_upload(owner.operation_id, owner.lease_id, owner.generation,
                                upload=SubmissionSourceUpload(intent=intent, provider_upload_id="recorded-handle"))
        await record_eof(session, owner.operation_id, owner.lease_id, owner.generation,
                         raw_sha256="sha256:" + hashlib.sha256(payload).hexdigest(), raw_byte_count=len(payload))



@pytest.mark.parametrize("admission_intake", ["no_pre", "no_post"], indirect=True)
async def test_t1_requires_one_selected_checker_in_each_phase(admission_intake):
    from sqlalchemy import func, select
    from app.modules.tasks.models import WorkstreamTask, AuditEvent
    f = admission_intake
    with pytest.raises(IntakeCustodyConflict, match="intake_requires_one_pre_and_post_checker"):
        await admit_new(f)
    async with f.factory() as session:
        assert await session.scalar(select(func.count()).select_from(SubmissionIntakeOperation)) == 0
        assert (await session.get(WorkstreamTask, str(f.task))).active_submission_operation_id is None
        assert not list(await session.scalars(select(AuditEvent).where(
            AuditEvent.action_id == "submission.intake.reserve")))


async def test_t1_cross_task_same_key_race_resolves_original_before_eligibility(admission_intake):
    from sqlalchemy import select, func
    from app.modules.artifacts.intake.foreground_admission import IntakeReservationOwner
    f = admission_intake
    other_task, other_assignment = new_record_id(), new_record_id()
    async with f.factory.kw["bind"].begin() as connection:
        await seed_started_task_for_artifact_test(connection, dict(
            task=str(other_task), assignment=str(other_assignment), project=str(f.project), actor=str(f.actor.actor_profile_id),
        ))
    key = new_record_id()
    selectors = [SubmissionIntakeMetadata(task_id=f.task, assignment_id=f.assignment),
                 SubmissionIntakeMetadata(task_id=other_task, assignment_id=other_assignment)]
    results = await asyncio.wait_for(asyncio.gather(
        *(admit_new(f, key=key, metadata=metadata) for metadata in selectors), return_exceptions=True,
    ), 10)
    assert sum(isinstance(value, IntakeReservationOwner) for value in results) == 1
    conflicts = [value for value in results if isinstance(value, IntakeCustodyConflict)]
    assert len(conflicts) == 1 and str(conflicts[0]) == "submission_idempotency_conflict"
    # Even a now-missing requested task resolves the old operation before eligibility.
    with pytest.raises(IntakeCustodyConflict, match="submission_idempotency_conflict"):
        await admit_new(f, key=key, metadata=SubmissionIntakeMetadata(task_id=new_record_id(), assignment_id=new_record_id()))
    async with f.factory() as session:
        assert await session.scalar(select(func.count()).select_from(SubmissionIntakeOperation)) == 1


async def test_t1_cancelled_discard_replay_does_not_terminalize_original(admission_intake):
    from app.modules.artifacts.intake.models import SubmissionSourceCharge
    f = admission_intake
    key = new_record_id()
    owner = await admit_new(f, key=key)
    await record_intake_eof(f, owner, b"raw ZIP")
    started, stopped = asyncio.Event(), asyncio.Event()

    async def body():
        try:
            started.set()
            await asyncio.Event().wait()
            yield b"never"
        finally:
            stopped.set()

    command = asyncio.create_task(f.admission.replay(
        SubmissionIntakeMetadata(task_id=f.task, assignment_id=f.assignment), body(),
        actor_id=f.actor.actor_profile_id, idempotency_key=key, declared_raw_bytes=None,
        idle_timeout_seconds=10, replay_duration=timedelta(seconds=30),
    ))
    try:
        await asyncio.wait_for(started.wait(), 10)
        command.cancel()
        with pytest.raises(asyncio.CancelledError):
            await command
    finally:
        command.cancel()
        await asyncio.gather(command, return_exceptions=True)
    assert stopped.is_set()
    async with f.factory() as session:
        row = await session.get(SubmissionIntakeOperation, str(owner.operation_id))
        assert row.state == "receiving" and row.lease_generation == owner.generation
        assert (await session.get(SubmissionSourceCharge, row.id)).accounted_bytes == 1024


@pytest.mark.parametrize("admission_intake", ["aws"], indirect=True)
async def test_t1_unqualified_aws_source_refuses_before_reservation(admission_intake):
    from sqlalchemy import func, select
    from app.modules.artifacts.intake.models import SubmissionSourceCharge
    from app.modules.tasks.models import WorkstreamTask
    f = admission_intake
    with pytest.raises(IntakeCustodyConflict, match="intake_source_provider_unqualified"):
        await admit_new(f)
    async with f.factory() as session:
        assert await session.scalar(select(func.count()).select_from(SubmissionIntakeOperation)) == 0
        assert await session.scalar(select(func.count()).select_from(SubmissionSourceCharge)) == 0
        assert (await session.get(WorkstreamTask, str(f.task))).active_submission_operation_id is None


async def test_t1_replay_reauthorizes_after_body_read(admission_intake):
    from app.modules.authorization.api.submission_intake import IntakeAuthorityDenied
    f = admission_intake
    key = new_record_id()
    owner = await admit_new(f, key=key)
    payload = b"raw ZIP"
    await record_intake_eof(f, owner, payload)

    async def body():
        yield payload
        response = await f.access.signed.client.post(
            f"/api/v1/projects/{f.project}/role-grants/{f.grant_id}/revoke",
            headers=f.manager.headers | {"Idempotency-Key": str(new_record_id())},
            json={"reason": "Withdraw grant during intake replay"},
        )
        assert response.status_code == 200, response.text

    with pytest.raises(IntakeAuthorityDenied):
        await asyncio.wait_for(f.admission.replay(
            SubmissionIntakeMetadata(task_id=f.task, assignment_id=f.assignment), body(),
            actor_id=f.actor.actor_profile_id, idempotency_key=key, declared_raw_bytes=None,
            idle_timeout_seconds=10, replay_duration=timedelta(seconds=20),
        ), 20)
    async with f.factory() as session:
        row = await session.get(SubmissionIntakeOperation, str(owner.operation_id))
        assert row.state == "receiving" and row.lease_generation == owner.generation
