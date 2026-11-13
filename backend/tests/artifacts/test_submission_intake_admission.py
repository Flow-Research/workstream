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
from tests.artifacts.intake_recovery_support import recovery_intake as recovery_intake
from tests.authorization.admin_access.fixtures import (
    signed_access as signed_access,
    admin_access as admin_access,
)


async def test_stalled_accepted_source_is_protected_from_cleanup(recovery_intake):
    """Exhausted finalizer delivery never turns accepted input into garbage."""
    from sqlalchemy.exc import DBAPIError
    from sqlalchemy import text
    from tests.artifacts.test_submission_source_cleanup import owner
    from tests.checkers.execution.support import provision_post_submit_service
    from app.modules.actors.api import ServiceIdentity
    f, operation = recovery_intake.f, recovery_intake.owner.operation_id
    await provision_post_submit_service(f.factory, ServiceIdentity.ARTIFACT_SOURCE_CLEANUP)
    with pytest.raises(DBAPIError, match="cleanup is protected"):
        async with f.factory.begin() as session:
            await owner(session).claim(
                operation, new_record_id(), lease_duration=timedelta(minutes=5))
    async with f.factory() as session:
        assert await session.scalar(text("SELECT state FROM submission_intake_operations WHERE id=:id"),
                                    {"id": operation}) == "finalization_pending"
        assert await session.scalar(text("SELECT accounted_bytes FROM submission_source_charges WHERE operation_id=:id"),
                                    {"id": operation}) > 0


@pytest.fixture
async def admission_intake(tmp_path, isolated_database_env, admin_access, request):
    from app.adapters.outbox import outbox_append, finalized_unknown_deliveries
    from app.adapters.projects import project_locked_policy_context_port
    from app.modules.artifacts.intake.foreground_admission import ForegroundIntakeAdmission
    from app.modules.authorization.submission_intake import SubmissionIntakeAuthorization
    from tests.authorization.task_authority.test_postgresql import context, grant, project_manager

    engine = create_async_engine(isolated_database_env)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    namespace = _namespace(_settings(tmp_path))
    source_store_factory = None
    if getattr(request, "param", None) == "minio":
        from tests.artifacts.intake_post_support import minio_source_fixture
        namespace, source_store_factory = await minio_source_fixture()
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
            events=outbox_append, deliveries=finalized_unknown_deliveries,
            capacity_limits=SubmissionSourceCapacityLimits(maximum_total_bytes=1_000_000), maximum_raw_bytes=1024,
            upload_duration=timedelta(seconds=300), lease_duration=timedelta(seconds=60),
        )
        yield SimpleNamespace(factory=factory, actor=actor, task=task, assignment=assignment,
                              admission=admission, project=project, namespace=namespace,
                              access=admin_access, manager=manager, grant_id=grant_id,
                              source_store_factory=source_store_factory)
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


async def test_t4_accepts_exact_source_and_replays_one_receipt(admission_intake, tmp_path):
    """T1/upload/PRE through the real atomic T4 owner; no formal Submission yet."""
    from sqlalchemy import text
    from app.adapters.checkers import selected_pre_submit_coordinator
    from app.adapters.outbox import outbox_append
    from tests.artifacts.intake_acceptance_support import completed_source
    f = admission_intake
    owner, request, terminal = await completed_source(f, tmp_path)
    kwargs = dict(checkers=selected_pre_submit_coordinator, outbox=outbox_append)
    receipt = await f.admission.accept(owner, request, terminal.terminal_digest, **kwargs)
    assert receipt["status"] == "accepted" and receipt["replayed"] is False
    assert receipt["operation_id"] == str(owner.operation_id)
    assert receipt["pre_submission_results"]
    assert await f.admission.accept(owner, request, terminal.terminal_digest, **kwargs) == dict(receipt, replayed=True)
    async with f.factory.begin() as session:
        row = await session.get(SubmissionIntakeOperation, str(owner.operation_id))
        assert row.state == "finalization_pending" and row.acceptance_receipt == receipt
        task = (await session.execute(text(
            "SELECT status, active_submission_operation_id FROM workstream_tasks WHERE id=:id"), {"id": f.task})).one()
        assert task.status == "evaluation_pending" and task.active_submission_operation_id == owner.operation_id
        assert await session.scalar(text("SELECT count(*) FROM submissions WHERE task_id=:id"), {"id": f.task}) == 0
        assert await session.scalar(text(
            "SELECT count(*) FROM artifact_bindings WHERE project_id=:id "
            "AND resource_type='submission'"), {"id": f.project}) == 0
        assert await session.scalar(text(
            "SELECT count(*) FROM submission_dispatches WHERE task_id=:id"), {"id": f.task}) == 0
        assert await session.scalar(text(
            "SELECT count(*) FROM checker_runs WHERE task_id=:id"), {"id": f.task}) == 0
        assert await session.scalar(text(
            "SELECT count(*) FROM outbox_events WHERE project_id=:id "
            "AND event_type='PostSubmissionEvaluationRequested'"), {"id": f.project}) == 0
        assert await session.scalar(text("SELECT count(*) FROM outbox_events WHERE aggregate_id=:id "
                                         "AND event_type='SubmissionFinalizationRequested'"), {"id": owner.operation_id}) == 1
        assert await session.scalar(text("SELECT count(*) FROM submission_source_charges WHERE operation_id=:id"),
                                    {"id": owner.operation_id}) == 1


@pytest.mark.parametrize("boundary", ["outbox", "task"])
async def test_t4_rolls_back_all_participants_and_can_retry(admission_intake, tmp_path, boundary):
    from sqlalchemy import text
    from app.adapters.checkers import selected_pre_submit_coordinator
    from app.adapters.outbox import outbox_append
    from tests.artifacts.intake_acceptance_support import completed_source
    f = admission_intake
    owner, request, terminal = await completed_source(f, tmp_path)
    original_tasks = f.admission._tasks

    class FailedOutbox:
        def __init__(self, session):
            self.delegate = outbox_append(session)
        async def append(self, event):
            await self.delegate.append(event)
            raise RuntimeError("injected handoff failure")

    class FailedTask(IntakeTaskCustody):
        async def accept(self, task_id, operation_id, expected_status):
            await super().accept(task_id, operation_id, expected_status)
            raise RuntimeError("injected handoff failure")

    if boundary == "task":
        f.admission._tasks = lambda session: FailedTask(session, task_submission_context_port(session))
    try:
        with pytest.raises(RuntimeError, match="injected handoff failure"):
            await f.admission.accept(owner, request, terminal.terminal_digest,
                checkers=selected_pre_submit_coordinator, outbox=FailedOutbox if boundary == "outbox" else outbox_append)
    finally:
        f.admission._tasks = original_tasks
    async with f.factory.begin() as session:
        row = await session.get(SubmissionIntakeOperation, str(owner.operation_id))
        assert row.state == "pre_checking" and row.accepted_at is None and row.finalization_event_id is None
        assert await session.scalar(text("SELECT status FROM workstream_tasks WHERE id=:id"), {"id": f.task}) == "in_progress"
        assert await session.scalar(text("SELECT count(*) FROM outbox_events WHERE aggregate_id=:id"),
                                    {"id": owner.operation_id}) == 0
        assert await session.scalar(text("SELECT count(*) FROM audit_events WHERE resource_id=:id AND action_id='submission.create'"),
                                    {"id": str(owner.operation_id)}) == 0
    receipt = await f.admission.accept(owner, request, terminal.terminal_digest,
        checkers=selected_pre_submit_coordinator, outbox=outbox_append)
    assert receipt["status"] == "accepted" and receipt["replayed"] is False


@pytest.mark.parametrize("case", ["concurrent", "lost_acknowledgement"])
async def test_t4_resolves_one_acceptance_under_duplicate_or_lost_response(admission_intake, tmp_path, case):
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import AsyncSession
    from app.adapters.checkers import selected_pre_submit_coordinator
    from app.adapters.outbox import outbox_append
    from tests.artifacts.intake_acceptance_support import completed_source
    f = admission_intake
    owner, request, terminal = await completed_source(f, tmp_path)
    kwargs = dict(checkers=selected_pre_submit_coordinator, outbox=outbox_append)
    if case == "concurrent":
        receipts = await asyncio.wait_for(asyncio.gather(*(
            f.admission.accept(owner, request, terminal.terminal_digest, **kwargs) for _ in range(2))), 20)
        assert sorted(receipt["replayed"] for receipt in receipts) == [False, True]
        assert dict(receipts[0], replayed=False) == dict(receipts[1], replayed=False)
    else:
        lost = False
        class LostAcknowledgement(AsyncSession):
            async def commit(self):
                nonlocal lost
                await super().commit()
                if not lost:
                    lost = True
                    raise ConnectionError("committed acceptance acknowledgement lost")
        f.admission._sessions = async_sessionmaker(f.factory.kw["bind"], class_=LostAcknowledgement, expire_on_commit=False)
        receipt = await f.admission.accept(owner, request, terminal.terminal_digest, **kwargs)
        assert lost and receipt["status"] == "accepted" and receipt["replayed"] is True
    async with f.factory.begin() as session:
        assert await session.scalar(text("SELECT count(*) FROM outbox_events WHERE aggregate_id=:id "
                                         "AND event_type='SubmissionFinalizationRequested'"), {"id": owner.operation_id}) == 1
        assert await session.scalar(text("SELECT count(*) FROM audit_events WHERE resource_id=:id AND action_id='submission.create'"),
                                    {"id": str(owner.operation_id)}) == 1


async def test_t4_accepted_custody_cannot_be_mutated_or_abandoned(admission_intake, tmp_path):
    from sqlalchemy import text
    from sqlalchemy.exc import DBAPIError
    from app.adapters.checkers import selected_pre_submit_coordinator
    from app.adapters.outbox import outbox_append
    from tests.artifacts.intake_acceptance_support import completed_source
    f = admission_intake
    owner, request, terminal = await completed_source(f, tmp_path)
    receipt = await f.admission.accept(owner, request, terminal.terminal_digest,
        checkers=selected_pre_submit_coordinator, outbox=outbox_append)
    async with f.factory.begin() as session:
        assert await repository(session).abandon_expired(owner.operation_id) is False
    for sql in (
        "UPDATE submission_intake_operations SET state='abandoned' WHERE id=:id",
        "UPDATE submission_intake_operations SET acceptance_receipt='{}'::jsonb WHERE id=:id",
        "UPDATE submission_intake_operations SET acceptance_decision_id=NULL WHERE id=:id",
        "UPDATE submission_intake_operations SET lease_expires_at=clock_timestamp()-interval '1 second' WHERE id=:id",
        "DELETE FROM submission_source_charges WHERE operation_id=:id",
        "UPDATE workstream_tasks SET active_submission_operation_id=NULL WHERE active_submission_operation_id=:id",
        "UPDATE workstream_tasks SET status='in_progress' WHERE active_submission_operation_id=:id",
    ):
        with pytest.raises(DBAPIError):
            async with f.factory.begin() as session:
                await session.execute(text(sql), {"id": owner.operation_id})
    assert await f.admission.accept(owner, request, terminal.terminal_digest,
        checkers=selected_pre_submit_coordinator, outbox=outbox_append) == dict(receipt, replayed=True)


@pytest.mark.parametrize("when", ["before", "after"])
async def test_t4_revocation_blocks_new_acceptance_but_preserves_accepted_custody(admission_intake, tmp_path, when):
    from sqlalchemy import text
    from app.adapters.checkers import selected_pre_submit_coordinator
    from app.adapters.outbox import outbox_append
    from app.modules.authorization.api.submission_intake import IntakeAuthorityDenied
    from tests.artifacts.intake_acceptance_support import completed_source
    f = admission_intake
    owner, request, terminal = await completed_source(f, tmp_path)
    if when == "after":
        await f.admission.accept(owner, request, terminal.terminal_digest,
            checkers=selected_pre_submit_coordinator, outbox=outbox_append)
    response = await f.access.signed.client.post(
        f"/api/v1/projects/{f.project}/role-grants/{f.grant_id}/revoke",
        headers=f.manager.headers | {"Idempotency-Key": str(new_record_id())},
        json={"reason": "Withdraw grant before accepted handoff"})
    assert response.status_code == 200, response.text
    with pytest.raises(IntakeAuthorityDenied):
        await f.admission.accept(owner, request, terminal.terminal_digest,
            checkers=selected_pre_submit_coordinator, outbox=outbox_append)
    async with f.factory.begin() as session:
        row = await session.get(SubmissionIntakeOperation, str(owner.operation_id))
        if when == "before":
            assert row.state == "pre_checking" and row.acceptance_decision_id is None and row.finalization_event_id is None
        else:
            assert row.state == "finalization_pending" and row.acceptance_receipt["status"] == "accepted"
            await session.execute(text("SELECT public.require_submission_acceptance(o) "
                "FROM submission_intake_operations o WHERE id=:id"), {"id": owner.operation_id})
            assert await repository(session).abandon_expired(owner.operation_id) is False


@pytest.mark.parametrize("winner", ["acceptance", "abandonment"])
async def test_t4_and_expiry_serialize_both_winner_orders(admission_intake, tmp_path, winner):
    from sqlalchemy import text
    from app.adapters.checkers import selected_pre_submit_coordinator
    from app.adapters.outbox import outbox_append
    from tests.artifacts.intake_acceptance_support import completed_source
    f = admission_intake
    owner, request, terminal = await completed_source(f, tmp_path)
    attempted, held, release = asyncio.Event(), asyncio.Event(), asyncio.Event()
    original_tasks = f.admission._tasks

    class ObservedTasks(IntakeTaskCustody):
        async def lock(self, task_id):
            attempted.set()
            return await super().lock(task_id)

    if winner == "abandonment":
        async with f.factory.begin() as session:
            await session.execute(text("UPDATE submission_intake_operations SET lease_expires_at="
                "clock_timestamp()-interval '1 second' WHERE id=:id"), {"id": owner.operation_id})
        f.admission._tasks = lambda session: ObservedTasks(session, task_submission_context_port(session))
        async with f.factory() as session:
            await session.begin()
            assert await repository(session).abandon_expired(owner.operation_id)
            command = asyncio.create_task(f.admission.accept(owner, request, terminal.terminal_digest,
                checkers=selected_pre_submit_coordinator, outbox=outbox_append))
            try:
                await asyncio.wait_for(attempted.wait(), 10)
                assert not command.done()
                await session.commit()
                with pytest.raises(IntakeCustodyConflict):
                    await asyncio.wait_for(command, 10)
            finally:
                command.cancel()
                await asyncio.gather(command, return_exceptions=True)
                f.admission._tasks = original_tasks
        expected = "abandoned"
    else:
        async with f.factory.begin() as session:
            await session.execute(text("UPDATE submission_intake_operations SET lease_expires_at="
                "clock_timestamp()+interval '5 seconds' WHERE id=:id"), {"id": owner.operation_id})
        class PausedOutbox:
            def __init__(self, session):
                self.delegate = outbox_append(session)
            async def append(self, event):
                result = await self.delegate.append(event)
                held.set()
                await release.wait()
                return result
        async def expire():
            from app.modules.artifacts.intake.repository import SubmissionIntakeRepository
            async with f.factory.begin() as session:
                tasks = ObservedTasks(session, task_submission_context_port(session))
                await tasks.lock(f.task)
                from tests.artifacts.intake_acceptance_support import wait_foreground_expired
                await wait_foreground_expired(session, owner.operation_id)
                return await SubmissionIntakeRepository(session, tasks).abandon_expired(owner.operation_id)
        command = asyncio.create_task(f.admission.accept(owner, request, terminal.terminal_digest,
            checkers=selected_pre_submit_coordinator, outbox=PausedOutbox))
        recovery = None
        try:
            await asyncio.wait_for(held.wait(), 10)
            recovery = asyncio.create_task(expire())
            await asyncio.wait_for(attempted.wait(), 10)
            assert not recovery.done()
            release.set()
            assert (await asyncio.wait_for(command, 10))["status"] == "accepted"
            assert await asyncio.wait_for(recovery, 10) is False
        finally:
            release.set()
            command.cancel()
            if recovery is not None:
                recovery.cancel()
            await asyncio.gather(command, *( [recovery] if recovery is not None else []), return_exceptions=True)
        expected = "finalization_pending"
    async with f.factory.begin() as session:
        row = await session.get(SubmissionIntakeOperation, str(owner.operation_id))
        assert row.state == expected
        assert (row.acceptance_receipt is not None) == (winner == "acceptance")
        assert await session.scalar(text("SELECT count(*) FROM outbox_events WHERE aggregate_id=:id"),
                                    {"id": owner.operation_id}) == int(winner == "acceptance")


async def test_t4_rejects_lease_expiry_at_commit_boundary(admission_intake, tmp_path):
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import AsyncSession
    from app.adapters.checkers import selected_pre_submit_coordinator
    from app.adapters.outbox import outbox_append
    from tests.artifacts.intake_acceptance_support import completed_source
    f = admission_intake
    owner, request, terminal = await completed_source(f, tmp_path)
    async with f.factory.begin() as session:
        await session.execute(text("UPDATE submission_intake_operations SET lease_expires_at="
            "clock_timestamp()+interval '5 seconds' WHERE id=:id"), {"id": owner.operation_id})
    delayed = False
    class ExpiredCommit(AsyncSession):
        async def commit(self):
            nonlocal delayed
            if not delayed:
                delayed = True
                from tests.artifacts.intake_acceptance_support import wait_foreground_expired
                await wait_foreground_expired(self, owner.operation_id)
            await super().commit()
    f.admission._sessions = async_sessionmaker(f.factory.kw["bind"], class_=ExpiredCommit, expire_on_commit=False)
    with pytest.raises(IntakeCustodyConflict, match="intake_acceptance_conflict"):
        await f.admission.accept(owner, request, terminal.terminal_digest,
            checkers=selected_pre_submit_coordinator, outbox=outbox_append)
    assert delayed
    async with f.factory.begin() as session:
        row = await session.get(SubmissionIntakeOperation, str(owner.operation_id))
        assert row.state == "pre_checking" and row.acceptance_receipt is None
        assert await session.scalar(text("SELECT status FROM workstream_tasks WHERE id=:id"), {"id": f.task}) == "in_progress"
        assert await session.scalar(text("SELECT count(*) FROM outbox_events WHERE aggregate_id=:id"),
                                    {"id": owner.operation_id}) == 0


async def test_t4_cancellation_drains_commit_and_keeps_accepted_custody(admission_intake, tmp_path):
    from sqlalchemy.ext.asyncio import AsyncSession
    from app.adapters.checkers import selected_pre_submit_coordinator
    from app.adapters.outbox import outbox_append
    from tests.artifacts.intake_acceptance_support import completed_source
    f = admission_intake
    owner, request, terminal = await completed_source(f, tmp_path)
    committed, release = asyncio.Event(), asyncio.Event()
    class DelayedAcknowledgement(AsyncSession):
        async def commit(self):
            await super().commit()
            committed.set()
            await release.wait()
    f.admission._sessions = async_sessionmaker(f.factory.kw["bind"], class_=DelayedAcknowledgement, expire_on_commit=False)
    kwargs = dict(checkers=selected_pre_submit_coordinator, outbox=outbox_append)
    command = asyncio.create_task(f.admission.accept(owner, request, terminal.terminal_digest, **kwargs))
    try:
        await asyncio.wait_for(committed.wait(), 10)
        command.cancel()
        await asyncio.sleep(0)
        assert not command.done()
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(command, 10)
    finally:
        release.set()
        command.cancel()
        await asyncio.gather(command, return_exceptions=True)
    receipt = await f.admission.accept(owner, request, terminal.terminal_digest, **kwargs)
    assert receipt["status"] == "accepted" and receipt["replayed"] is True


@pytest.mark.parametrize("expired_claim", [False, True])
async def test_t5_finalizes_same_source_with_one_submission_and_post_dispatch(admission_intake, tmp_path, expired_claim):
    from datetime import timedelta
    from sqlalchemy import text
    from app.adapters.artifacts import submission_admission_consumption_port
    from app.adapters.checkers import selected_pre_submit_coordinator
    from app.adapters.outbox import outbox_append
    from app.adapters.tasks import accepted_submission_creation_service
    from app.modules.actors.api import ServiceIdentity
    from app.modules.artifacts.authorization import PreparedSubmissionFinalizationAuthorization
    from app.modules.artifacts.intake.finalization import AcceptedSubmissionFinalization
    from tests.artifact_store_helpers import initialize_local_store
    from tests.artifacts.intake_acceptance_support import completed_source
    from tests.checkers.execution.support import provision_post_submit_service

    f = admission_intake
    owner, request, terminal = await completed_source(f, tmp_path)
    accepted = await f.admission.accept(owner, request, terminal.terminal_digest,
        checkers=selected_pre_submit_coordinator, outbox=outbox_append)
    await provision_post_submit_service(f.factory, ServiceIdentity.ARTIFACT_BINDING)
    store = initialize_local_store(root=tmp_path / "durable", buffer_bytes=256 * 1024)
    def submissions(session):
        return accepted_submission_creation_service(session, settings=_settings(tmp_path),
            admissions=submission_admission_consumption_port(session,
                request_id=new_record_id(), correlation_id=owner.operation_id))
    finalizer = AcceptedSubmissionFinalization(
        f.factory, tasks=f.admission._tasks, submissions=submissions,
        checkers=selected_pre_submit_coordinator, store=store, lease_duration=timedelta(seconds=60),
        authorization=lambda session: PreparedSubmissionFinalizationAuthorization(
            session, request_id=new_record_id(), correlation_id=owner.operation_id),
    )
    try:
        if expired_claim:
            from tests.artifacts.intake_post_support import leave_expired_finalizer_claim
            await leave_expired_finalizer_claim(f, finalizer, owner.operation_id)
        result = await finalizer.run(owner.operation_id)
        assert await finalizer.run(owner.operation_id) == result
        assert await f.admission.accept(owner, request, terminal.terminal_digest,
            checkers=selected_pre_submit_coordinator, outbox=outbox_append) == dict(accepted, replayed=True)
        async with f.factory() as session:
            row = await session.get(SubmissionIntakeOperation, str(owner.operation_id))
            assert row.state == "finalized" and row.finalized_submission_id == str(result.submission_id)
            assert row.continuation_generation == (2 if expired_claim else 1)
            task = (await session.execute(text("SELECT status, active_submission_operation_id "
                "FROM workstream_tasks WHERE id=:id"), {"id": f.task})).one()
            assert task.status == "evaluation_pending" and task.active_submission_operation_id is None
            admission = (await session.execute(text("SELECT source_operation_id, durable_intent_id, put_attempt_id, "
                "verification_receipt_id FROM submission_bundle_admissions WHERE id=:id"),
                {"id": result.admission_id})).one()
            assert admission.source_operation_id == owner.operation_id
            assert admission.durable_intent_id is admission.put_attempt_id is admission.verification_receipt_id is None
            replica = (await session.execute(text("SELECT provider_object_ref FROM artifact_replicas "
                "WHERE source_operation_id=:id"), {"id": owner.operation_id})).one()
            assert replica.provider_object_ref == request.source.location.object_ref
            for table in ("submissions", "submission_dispatches", "checker_runs"):
                assert await session.scalar(text(f"SELECT count(*) FROM {table} WHERE task_id=:id"), {"id": f.task}) == 1
            assert await session.scalar(text("SELECT count(*) FROM outbox_events WHERE project_id=:id "
                "AND event_type='PostSubmissionEvaluationRequested'"), {"id": f.project}) == 1
            assert await session.scalar(text("SELECT count(*) FROM submission_source_charges WHERE operation_id=:id"),
                {"id": owner.operation_id}) == 1
        # Removing retained provenance must fail at commit even when all other
        # replica coordinates remain unchanged.
        from sqlalchemy.exc import IntegrityError
        async with f.factory() as session:
            with pytest.raises(IntegrityError, match="retained source ownership is immutable"):
                async with session.begin():
                    await session.execute(text("UPDATE artifact_replicas SET source_operation_id=NULL "
                        "WHERE source_operation_id=:id"), {"id": owner.operation_id})
        substitutions = (
            ("UPDATE artifact_contents SET sha256='sha256:' || repeat('f',64) WHERE id=:id",
             result.artifact_content_id, "accepted source content is immutable"),
            ("UPDATE artifact_contents SET byte_count=byte_count+1 WHERE id=:id",
             result.artifact_content_id, "accepted source content is immutable"),
            ("UPDATE artifact_contents SET media_type='application/octet-stream' WHERE id=:id",
             result.artifact_content_id, "accepted source content is immutable"),
            ("UPDATE artifact_replicas SET adapter='substituted' WHERE source_operation_id=:id",
             owner.operation_id, "source admission provenance mismatch"),
        )
        for statement, identity, message in substitutions:
            async with f.factory() as session:
                with pytest.raises(IntegrityError, match=message):
                    async with session.begin():
                        await session.execute(text(statement), {"id": identity})
        from tests.artifacts.intake_post_support import exercise_source_post
        await exercise_source_post(f, result, store, request.source, tmp_path)
    finally:
        store.close()


async def test_operator_recovers_same_accepted_finalization_once(recovery_intake, tmp_path):
    import asyncio
    from sqlalchemy import select, func
    from app.adapters.artifacts.finalization import submission_finalization_recovery_handler
    from app.adapters.auth import outbox_dispatch_authorization
    from app.adapters.outbox import outbox_delivery
    from app.modules.artifacts.api.submission_recovery import FINALIZATION_RECOVERY_EVENT, SubmissionRecoveryUnavailable
    from app.modules.outbox.api import DeliveryOptions
    from app.modules.outbox.models import OutboxEvent
    from app.modules.outbox.registry import HandlerRegistry
    from app.modules.tasks.models import Submission
    from tests.artifact_store_helpers import initialize_local_store

    r = recovery_intake
    f, owner, event_id = r.f, r.owner, r.event_id
    metadata, intake_key, command, recover = r.metadata, r.intake_key, r.command, r.recover
    with pytest.raises(SubmissionRecoveryUnavailable):
        await recover()
    grant_id = await f.access.signed.grant(f.access.admin, f.access.target)
    created, raced = await asyncio.gather(recover(), recover())
    assert raced == created and await recover() == created
    with pytest.raises(SubmissionRecoveryUnavailable, match="submission_recovery_conflict"):
        await recover(command.model_copy(update={"reason": "Different recovery reason"}))
    progress = await f.admission._read(metadata, f.actor.actor_profile_id, intake_key)
    assert not progress.finalization.operationally_stalled and progress.finalization.next_retry_at is not None
    store = initialize_local_store(root=tmp_path / "durable", buffer_bytes=256 * 1024)
    try:
        handler = submission_finalization_recovery_handler(sessions=f.factory,
            settings=_settings(tmp_path), store=store, lease_duration=timedelta(seconds=30))
        invocations = []
        async def invoke(envelope):
            invocations.append(envelope)
            result = await handler(envelope)
            if len(invocations) == 1:
                raise RuntimeError("lost recovery acknowledgement after T5")
            return result
        options = DeliveryOptions(lease_seconds=30, handler_timeout_seconds=25, max_attempts=2,
                                  retry_base_seconds=1, retry_cap_seconds=1)
        retry = outbox_delivery(f.factory, authorization_factory=outbox_dispatch_authorization,
            registry=HandlerRegistry([(FINALIZATION_RECOVERY_EVENT, 1, invoke)],
                replay_safe=frozenset({(FINALIZATION_RECOVERY_EVENT, 1)})), options=options)
        await retry.deliver(created.recovery_event_id, f.project, "recovery-finalizer")
        await asyncio.sleep(1.05)
        await retry.deliver(created.recovery_event_id, f.project, "recovery-replay")
        with pytest.raises(SubmissionRecoveryUnavailable, match="submission_recovery_stale"):
            await handler(invocations[0])
        replayed = await recover()
        assert replayed.recovery_event_id == created.recovery_event_id and replayed.state == "acknowledged"
        async with f.factory() as session:
            row = await session.get(SubmissionIntakeOperation, str(owner.operation_id))
            assert row.state == "finalized" and row.finalization_event_id == str(event_id)
            assert await session.scalar(select(func.count()).select_from(Submission).where(
                Submission.task_id == str(f.task))) == 1
            assert await session.scalar(select(func.count()).select_from(OutboxEvent).where(
                OutboxEvent.event_type == "PostSubmissionEvaluationRequested")) == 1
            assert (await session.get(OutboxEvent, event_id)).delivery_state == "dead_letter"
            assert await session.scalar(select(func.count()).select_from(OutboxEvent).where(
                OutboxEvent.event_type == FINALIZATION_RECOVERY_EVENT)) == 1
        final = await f.admission._read(metadata, f.actor.actor_profile_id, intake_key)
        assert final.finalization.finalized and not final.finalization.operationally_stalled
        assert final.finalization.attempt_count == 3 and final.finalization.next_retry_at is None
        revoked = await f.access.signed.revoke(f.access.admin, grant_id)
        assert revoked.status_code == 200, revoked.text
        with pytest.raises(SubmissionRecoveryUnavailable):
            await recover()
    finally:
        store.close()


@pytest.mark.parametrize("duration", [timedelta(0), timedelta(days=3650), timedelta(hours=1, microseconds=1)])
def test_finalization_rejects_unbounded_or_empty_lease(duration):
    from app.modules.artifacts.intake.finalization import AcceptedSubmissionFinalization
    with pytest.raises(ValueError, match="at most one hour"):
        AcceptedSubmissionFinalization(None, tasks=None, authorization=None, submissions=None,
            checkers=None, store=None, lease_duration=duration)


async def test_recovery_sql_requires_exact_source_and_real_operator_cause(recovery_intake):
    import json
    from sqlalchemy import text
    from sqlalchemy.exc import IntegrityError
    from app.adapters.auth import submission_recovery_authorization
    from app.modules.artifacts.api.submission_recovery import SubmissionRecoveryPayload
    from tests.artifacts.intake_recovery_support import insert_recovery_payload, forge_recovery_audit

    r, f = recovery_intake, recovery_intake.f
    await f.access.signed.grant(f.access.admin, f.access.target)
    async with f.factory.begin() as session:
        authority = await submission_recovery_authorization(session, r.context).authorize(r.command, r.source)
        foreign_link = await session.scalar(text(
            "SELECT id FROM actor_identity_links WHERE actor_profile_id=:actor"), {"actor": f.access.admin.id})
    original = SubmissionRecoveryPayload(command=r.command, source=r.source, authority=authority).model_dump(mode="json")
    cases = (
        ("reason", "recovery authority shape differs"),
        ("decision", "recovery retained Operator cause differs"),
        ("source", "recovery exact source or command differs"),
        ("digest", "recovery payload digest differs"),
        ("grant", "recovery retained Operator cause differs"),
        ("wrong_grant", "recovery retained Operator cause differs"),
        ("link", "recovery retained Operator cause differs"),
        ("target", "recovery retained Operator cause differs"),
        ("unicode_reason", "recovery exact source or command differs"),
    )
    for case, message in cases:
        payload, patch = json.loads(json.dumps(original)), {}
        if case == "reason":
            payload["command"]["reason"] = "Forged reason"
        elif case == "decision":
            payload["authority"]["decision_id"] = str(new_record_id())
        elif case == "source":
            payload["source"]["task_id"] = str(new_record_id())
        elif case == "grant":
            patch["matched_grant_id"] = None
        elif case == "wrong_grant":
            patch["matched_grant_id"] = f.access.bootstrap_grant_id
        elif case == "link":
            payload["authority"]["identity_link_id"] = str(foreign_link)
        elif case == "target":
            patch.update(target_ref_kind="project", target_ref_id=str(f.project))
        elif case == "unicode_reason":
            payload["command"]["reason"] = "\u00a0"
        with pytest.raises(IntegrityError, match=message):
            async with f.factory.begin() as session:
                if case not in {"reason", "decision", "digest"}:
                    await forge_recovery_audit(session, authority.decision_id, payload, patch)
                await insert_recovery_payload(session, payload,
                    digest="sha256:" + "0" * 64 if case == "digest" else None)
    async with f.factory.begin() as session:
        assert await session.scalar(text("SELECT count(*) FROM outbox_events "
            "WHERE event_type='SubmissionFinalizationRecoveryRequested'")) == 0
        valid_id = await insert_recovery_payload(session, original)
    assert (await r.recover()).recovery_event_id == valid_id


@pytest.mark.parametrize("lost_at", ["after_commit", "during_observation"])
async def test_finalization_outbox_recovers_lost_ack_without_provider_replay(admission_intake, tmp_path, lost_at):
    from uuid import UUID
    from sqlalchemy import select, func, text
    from app.adapters.artifacts.finalization import submission_finalization_handler
    from app.adapters.auth import outbox_dispatch_authorization
    from app.adapters.checkers import selected_pre_submit_coordinator
    from app.adapters.outbox import outbox_append, outbox_delivery, production_outbox_delivery
    from app.modules.actors.api import ServiceIdentity
    from app.modules.outbox.api import DeliveryOptions, FinalizationCause, HandlerOutcome
    from app.modules.outbox.models import OutboxEvent
    from app.modules.outbox.registry import HandlerRegistry
    from tests.artifact_store_helpers import initialize_local_store
    from tests.artifacts.intake_acceptance_support import completed_source
    from tests.checkers.execution.support import provision_post_submit_service

    f = admission_intake
    owner, request, terminal = await completed_source(f, tmp_path)
    await f.admission.accept(owner, request, terminal.terminal_digest,
        checkers=selected_pre_submit_coordinator, outbox=outbox_append)
    for identity in (ServiceIdentity.ARTIFACT_BINDING, ServiceIdentity.OUTBOX_DISPATCHER):
        await provision_post_submit_service(f.factory, identity)
    store = initialize_local_store(root=tmp_path / "durable", buffer_bytes=256 * 1024)
    observations, invocations = [], []
    class ObservedStore:
        async def observe_sealed_source(self, source):
            observations.append(source)
            if lost_at == "during_observation" and len(observations) == 1:
                await delivery.finalize(invocations[0].claim, FinalizationCause.UNKNOWN)
            assert len(observations) <= (2 if lost_at == "during_observation" else 1)
            return await store.observe_sealed_source(source)
    handler = submission_finalization_handler(sessions=f.factory, settings=_settings(tmp_path),
        store=ObservedStore(), lease_duration=timedelta(seconds=30))
    async def lose_ack(envelope):
        invocations.append(envelope)
        assert await handler(envelope.model_copy(update={"aggregate_id": new_record_id()})) == HandlerOutcome.REJECT
        result = await handler(envelope)
        assert result == HandlerOutcome.ACKNOWLEDGE
        if len(invocations) == 1 and lost_at == "after_commit":
            raise RuntimeError("worker lost after committed T5")
        return result
    event_type = "SubmissionFinalizationRequested"
    delivery = outbox_delivery(f.factory, authorization_factory=outbox_dispatch_authorization,
        registry=HandlerRegistry([(event_type, 1, lose_ack)], replay_safe=frozenset({(event_type, 1)})),
        options=DeliveryOptions(lease_seconds=10, handler_timeout_seconds=9,
                                retry_base_seconds=1, retry_cap_seconds=1))
    try:
        async with f.factory() as session:
            row = await session.get(SubmissionIntakeOperation, str(owner.operation_id))
            event_id = UUID(row.finalization_event_id)
        candidates = await production_outbox_delivery(f.factory).candidates()
        assert event_id in {item.event_id for item in candidates.items}
        assert await delivery.deliver(event_id, f.project, "first-worker") is not None
        async with f.factory() as session:
            row = await session.get(SubmissionIntakeOperation, str(owner.operation_id))
            event = await session.get(OutboxEvent, event_id)
            assert row.state == ("finalized" if lost_at == "after_commit" else "finalization_pending")
            assert event.delivery_state == "retryable"
            submission_id = row.finalized_submission_id
            assert row.continuation_expires_at <= invocations[0].claim.claim_expires_at
            ready_at = event.next_attempt_at
            if lost_at == "during_observation":
                assert submission_id is None
                ready_at = max(ready_at, row.continuation_expires_at)
            remaining = (ready_at - await session.scalar(select(func.clock_timestamp()))).total_seconds()
        await asyncio.sleep(max(0, remaining) + 0.05)
        assert await delivery.deliver(event_id, f.project, "replacement-worker") is not None
        async with f.factory() as session:
            row = await session.get(SubmissionIntakeOperation, str(owner.operation_id))
            event = await session.get(OutboxEvent, event_id)
            assert row.state == "finalized"
            if lost_at == "after_commit":
                assert row.finalized_submission_id == submission_id and row.continuation_generation == 1
            else:
                assert row.finalized_submission_id is not None and row.continuation_generation == 2
            assert event.delivery_state == "acknowledged" and event.attempt_count == 2
            for table in ("submissions", "submission_dispatches", "checker_runs"):
                assert await session.scalar(text(f"SELECT count(*) FROM {table} WHERE task_id=:id"),
                                            {"id": f.task}) == 1
            assert await session.scalar(text("SELECT count(*) FROM outbox_events WHERE project_id=:id "
                "AND event_type='PostSubmissionEvaluationRequested'"), {"id": f.project}) == 1
        assert len(observations) == (1 if lost_at == "after_commit" else 2)
        assert len(invocations) == 2
        assert await handler(invocations[0]) == HandlerOutcome.REJECT
    finally:
        store.close()


@pytest.mark.parametrize("effect_committed", [False, True])
async def test_authorized_progress_reports_exact_exhaustion_without_reopening_intake(
    admission_intake, tmp_path, monkeypatch, effect_committed,
):
    import json
    from uuid import UUID
    from sqlalchemy import select, func
    from app.adapters.artifacts.finalization import submission_finalization_handler
    from app.adapters.auth import outbox_dispatch_authorization
    from app.adapters.checkers import selected_pre_submit_coordinator
    from app.adapters.outbox import outbox_append, outbox_delivery
    from app.modules.actors.api import ServiceIdentity
    from app.modules.authorization.api.submission_intake import IntakeAuthorityDenied
    from app.modules.outbox.api import DeliveryOptions
    from app.modules.outbox.models import OutboxEvent, OutboxDeliveryAttempt
    from app.modules.outbox.registry import HandlerRegistry
    from app.modules.tasks.models import WorkstreamTask
    from tests.artifact_store_helpers import initialize_local_store
    from tests.artifacts.intake_acceptance_support import completed_source
    from tests.checkers.execution.support import provision_post_submit_service

    f = admission_intake
    owner, request, terminal = await completed_source(f, tmp_path)
    await f.admission.accept(owner, request, terminal.terminal_digest,
        checkers=selected_pre_submit_coordinator, outbox=outbox_append)
    for identity in (ServiceIdentity.ARTIFACT_BINDING, ServiceIdentity.OUTBOX_DISPATCHER):
        await provision_post_submit_service(f.factory, identity)
    async with f.factory() as session:
        row = await session.get(SubmissionIntakeOperation, str(owner.operation_id))
        key, event_id = UUID(row.idempotency_key), UUID(row.finalization_event_id)
        metadata = SubmissionIntakeMetadata.model_validate_json(json.dumps(row.command_metadata))
    async def read():
        return await f.admission._read(metadata, f.actor.actor_profile_id, key)
    initial = await read()
    assert initial.finalization.attempt_count == 0 and not initial.finalization.operationally_stalled
    store = initialize_local_store(root=tmp_path / "durable", buffer_bytes=256 * 1024)
    handler = submission_finalization_handler(sessions=f.factory, settings=_settings(tmp_path),
        store=store, lease_duration=timedelta(seconds=30))
    async def fail(envelope):
        active = await read()
        assert active.finalization.attempt_count == 1 and not active.finalization.operationally_stalled
        if effect_committed:
            await handler(envelope)
        raise RuntimeError("simulated worker loss")
    kind = "SubmissionFinalizationRequested"
    delivery = outbox_delivery(f.factory, authorization_factory=outbox_dispatch_authorization,
        registry=HandlerRegistry([(kind, 1, fail)], replay_safe=frozenset({(kind, 1)})),
        options=DeliveryOptions(lease_seconds=30, handler_timeout_seconds=25, max_attempts=1))
    try:
        assert await delivery.deliver(event_id, f.project, "exhausted-worker") is not None
        progress = await read()
        assert progress.failure_code is None
        assert progress.state == ("finalized" if effect_committed else "finalization_pending")
        assert progress.finalization.finalized is effect_committed
        assert progress.finalization.operationally_stalled is not effect_committed
        assert progress.finalization.next_retry_at is None and progress.finalization.attempt_count == 1
        assert (await read()).finalization == progress.finalization
        async with f.factory() as session:
            event = await session.get(OutboxEvent, event_id)
            task = await session.get(WorkstreamTask, str(f.task))
            assert event.delivery_state == "dead_letter" and event.last_error_code == "INVOKE_OUTCOME_UNKNOWN"
            assert progress.finalization.stalled_at == (None if effect_committed else event.finalized_at)
            assert task.status == "evaluation_pending"
            assert task.active_submission_operation_id == (None if effect_committed else str(owner.operation_id))
            assert await session.scalar(select(func.count()).select_from(OutboxDeliveryAttempt)) == 1
        revoked = await f.access.signed.client.post(
            f"/api/v1/projects/{f.project}/role-grants/{f.grant_id}/revoke",
            headers=f.manager.headers | {"Idempotency-Key": str(new_record_id())},
            json={"reason": "Withdraw progress read grant"},
        )
        assert revoked.status_code == 200, revoked.text
        def forbidden(_session):
            pytest.fail("denied read consulted delivery facts")
        monkeypatch.setattr(f.admission, "_events", forbidden)
        with pytest.raises(IntakeAuthorityDenied):
            await read()
    finally:
        store.close()
