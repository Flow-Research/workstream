"""Real owner/AUTH operations meet at an observed PostgreSQL TASK row wait."""

import asyncio

import pytest

from sqlalchemy import select, func

from app.core.identifiers import new_record_id
from app.modules.checkers.models import CheckerRun
from app.modules.outbox.models import OutboxEvent
from app.modules.tasks.models import Submission, SubmissionDispatch
from tests.post_submit_materialization_helpers import _material_fixture, _read_current_request, _submit_current_source
from tests.artifacts.test_submission_intake_admission import (
    admission_intake as admission_intake,
    admin_access as admin_access,
    auth_database_env as auth_database_env,
    clear_settings_cache as clear_settings_cache,
    rsa_signing_material as rsa_signing_material,
    signed_access as signed_access,
)


@pytest.mark.parametrize("contender", ["duplicate_delivery", "new_intake_key"])
async def test_concurrent_initial_creation_has_one_committed_dispatch(admission_intake, tmp_path, monkeypatch, contender):
    """A live T5 owner excludes duplicate delivery and a competing task intake."""
    from datetime import timedelta
    from uuid import UUID
    from app.adapters.artifacts import submission_finalization_handler
    from app.adapters.auth import outbox_dispatch_authorization
    from app.adapters.checkers import selected_pre_submit_coordinator
    from app.adapters.outbox import outbox_append, outbox_delivery
    from app.modules.actors.api import ServiceIdentity
    from app.modules.artifacts.api.submission_intake import SubmissionIntakeMetadata
    from app.modules.artifacts.intake.models import SubmissionIntakeOperation
    from app.modules.outbox.api import DeliveryOptions
    from app.modules.outbox.registry import HandlerRegistry
    from app.modules.tasks.api import TaskSubmissionContextUnavailable
    from tests.artifact_store_helpers import initialize_local_store
    from tests.artifacts.intake_acceptance_support import completed_source
    from tests.checkers.execution.support import provision_post_submit_service
    from tests.test_artifact_admission import _settings

    f = admission_intake
    owner, request, terminal = await completed_source(f, tmp_path)
    await f.admission.accept(owner, request, terminal.terminal_digest,
                            checkers=selected_pre_submit_coordinator, outbox=outbox_append)
    for identity in (ServiceIdentity.ARTIFACT_BINDING, ServiceIdentity.OUTBOX_DISPATCHER):
        await provision_post_submit_service(f.factory, identity)
    store = initialize_local_store(root=tmp_path / "durable", buffer_bytes=65536)
    held, release, observations = asyncio.Event(), asyncio.Event(), []
    observe = store.observe_sealed_source

    async def pause_observation(source):
        observations.append(source)
        held.set()
        await release.wait()
        return await observe(source)

    monkeypatch.setattr(store, "observe_sealed_source", pause_observation)
    handler = submission_finalization_handler(sessions=f.factory, settings=_settings(tmp_path),
                                             store=store, lease_duration=timedelta(seconds=120))
    kind = "SubmissionFinalizationRequested"
    delivery = outbox_delivery(f.factory, authorization_factory=outbox_dispatch_authorization,
        registry=HandlerRegistry([(kind, 1, handler)], replay_safe=frozenset({(kind, 1)})),
        options=DeliveryOptions(lease_seconds=180, handler_timeout_seconds=150))
    async with f.factory() as session:
        row = await session.get(SubmissionIntakeOperation, owner.operation_id)
        event_id = UUID(row.finalization_event_id)
    first = asyncio.create_task(delivery.deliver(event_id, f.project, "first-finalizer"))
    try:
        await asyncio.wait_for(held.wait(), 30)
        assert not first.done()
        if contender == "duplicate_delivery":
            assert await delivery.deliver(event_id, f.project, "second-finalizer") is None
        else:
            with pytest.raises(TaskSubmissionContextUnavailable):
                await f.admission.admit(SubmissionIntakeMetadata(task_id=f.task, assignment_id=f.assignment),
                    actor_id=f.actor.actor_profile_id, identity_link_id=f.actor.identity_link_id,
                    idempotency_key=new_record_id(), declared_raw_bytes=None)
        release.set()
        assert await asyncio.wait_for(first, 45) is not None
        await delivery.deliver(event_id, f.project, "replay-finalizer")
        assert observations == [request.source]
        async with f.factory() as session:
            row = await session.get(SubmissionIntakeOperation, owner.operation_id)
            assert row.state == "finalized"
            for model in (SubmissionIntakeOperation, Submission, SubmissionDispatch, CheckerRun):
                assert await session.scalar(select(func.count()).select_from(model).where(model.task_id == str(f.task))) == 1
            for event_type in (kind, "PostSubmissionEvaluationRequested"):
                assert await session.scalar(select(func.count()).select_from(OutboxEvent).where(
                    OutboxEvent.project_id == str(f.project), OutboxEvent.event_type == event_type)) == 1
    finally:
        release.set()
        if not first.done():
            first.cancel()
        await asyncio.gather(first, return_exceptions=True)
        store.close()


async def _role_race(tmp_path, database_url, monkeypatch, operation):
    from uuid import UUID
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
    from auth_concurrency_support import wait_for_named_database_lock
    from project_create_fixtures import grant_fixture_admin_role
    from app.modules.authorization import router
    from app.modules.authorization.models import ProjectRoleGrant
    from app.modules.authorization.project_role_schemas import ProjectRoleGrantRevokeBody
    from app.modules.authorization.submission_intake import SubmissionIntakeAuthorization
    from app.modules.tasks.models import WorkstreamTask
    from tests.test_artifact_admission import _context, _seed_human_actor
    from tests.project_role_issue_fixtures import issue_body, issue_runtime

    async def writer(factory, context, command, request, data):
        manager = _context()
        async with factory.begin() as session:
            project_id = UUID((await session.get(WorkstreamTask, str(request.task_id))).project_id)
            grant_id = await session.scalar(select(ProjectRoleGrant.id).where(
                ProjectRoleGrant.project_id == str(project_id),
                ProjectRoleGrant.actor_profile_id == str(context.actor_profile_id),
                ProjectRoleGrant.role == "submitter", ProjectRoleGrant.status == "active",
            ))
            await _seed_human_actor(session, manager)
            await grant_fixture_admin_role(session, manager.actor_profile_id, role="project_manager",
                                           scope="project", project_id=project_id)
        held, release = asyncio.Event(), asyncio.Event()
        original = SubmissionIntakeAuthorization.prepare_acceptance
        async def pause_after_authority(self, facts):
            handle = await original(self, facts)
            held.set()
            await asyncio.wait_for(release.wait(), 30)
            return handle
        name = "dispatch-role-" + new_record_id().hex
        engine = create_async_engine(database_url, connect_args={"server_settings": {"application_name": name}})
        role_factory = async_sessionmaker(engine, expire_on_commit=False)
        async def create():
            return await _submit_current_source(factory, context, command, request, data)
        async def mutate():
            async with role_factory() as session:
                prepared, resolved = await issue_runtime(
                    session, manager.actor_profile_id, manager.identity_link_id
                )
                if operation == "issue":
                    return await router.issue_project_role_grant(
                        project_id=project_id, payload=issue_body(context.actor_profile_id),
                        idempotency_key=new_record_id(), resolved=resolved, prepared=prepared, session=session,
                    )
                return await router.revoke_project_role_grant(
                    project_id=project_id, grant_id=grant_id,
                    payload=ProjectRoleGrantRevokeBody(reason="Concurrent contribution authority revocation"),
                    idempotency_key=new_record_id(), resolved=resolved, prepared=prepared, session=session,
                )
        pending = []
        try:
            with monkeypatch.context() as patch:
                patch.setattr(SubmissionIntakeAuthorization, "prepare_acceptance", pause_after_authority)
                pending.append(asyncio.create_task(create()))
                await asyncio.wait_for(held.wait(), 30)
                pending.append(asyncio.create_task(mutate()))
                await asyncio.wait_for(wait_for_named_database_lock(database_url, name), 30)
                release.set()
                created, changed = await asyncio.wait_for(asyncio.gather(*pending), 45)
                assert changed.status == ("active" if operation == "issue" else "revoked")
                return created
        finally:
            release.set()
            for task in pending:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*pending, return_exceptions=True)
            await engine.dispose()

    async with _material_fixture(tmp_path, database_url, submit_source=writer,
                                 read_request=_read_current_request) as h:
        async with h.factory() as session:
            assert await session.scalar(select(func.count()).select_from(SubmissionDispatch)) == 1
            assert await session.scalar(select(func.count()).select_from(CheckerRun)) == 1


async def test_role_issuance_serializes_with_submission_authority(tmp_path, isolated_database_env, monkeypatch):
    await _role_race(tmp_path, isolated_database_env, monkeypatch, "issue")


async def test_role_revocation_serializes_with_submission_authority(tmp_path, isolated_database_env, monkeypatch):
    await _role_race(tmp_path, isolated_database_env, monkeypatch, "revoke")
