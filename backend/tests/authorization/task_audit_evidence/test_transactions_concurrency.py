"""Real authorization serialization and caller-owned response rollback."""
import asyncio
from uuid import UUID

import pytest
from sqlalchemy import text

from app.adapters.audit import task_transition_audit
from app.adapters.tasks import task_commands
from app.core.config import get_settings
from app.db import session as db_session
from app.modules.authorization.task_authorization import PreparedTaskAuthorization
from app.modules.tasks.api import TaskAuthorityDenied
from app.modules.tasks.api.audit_evidence import AuditTaskEvidenceRequest
from tests.auth_concurrency_support import wait_for_named_database_lock
from tests.authorization.guide_activation.pg_support import revoke_manager_grant
from tests.authorization.task_authority.test_concurrency import actor_context
from tests.authorization.task_reads.support import task_case
from tests.authorization.task_audit_evidence.support import ACTION, grant_audit, path


@pytest.mark.parametrize("failure", ("projection", "serialization", "validation", "reference"))
async def test_post_consume_rollback(admin_access, monkeypatch, failure):
    from pydantic import TypeAdapter
    from app.modules.tasks.models import WorkstreamTask
    from app.modules.tasks.repository import TaskRepository
    from app.modules.tasks.service import TaskValidationError
    from tests.authorization.task_locked_context.test_transactions import count
    from tests.tasks.test_audit_evidence import NOW, store_event
    project, _, task = await task_case(admin_access)
    await grant_audit(admin_access, project)
    actor = await actor_context(str(admin_access.target.id))
    factory = db_session.get_session_factory()
    if failure == "reference":
        async with factory() as initial, initial.begin():
            await store_event(initial, str(task), when=NOW, event_type="TaskClaimed", typed_source=True,
                payload={"references": {"project_id": str(project), "task_id": str(task),
                    "assignment_id": "invalid-reference", "authorization_decision_id": str(project)}})
    async with factory() as session:
        original_title = (await session.get(WorkstreamTask, str(task))).title
    staged = []
    async with factory() as session:
        authority = PreparedTaskAuthorization(session, actor)
        command = task_commands(session, settings=get_settings(), authorization=authority,
                               audit=task_transition_audit(session), actor_profile_id=actor.actor_profile_id)
        original_consume = authority.consume
        async def observe(handle, facts):
            result = await original_consume(handle, facts)
            assert await count(session, actor.actor_profile_id, ACTION) == 1
            async with factory() as observer:
                assert await count(observer, actor.actor_profile_id, ACTION) == 0
            row = await session.get(WorkstreamTask, str(task))
            row.title = "uncommitted evidence read marker"
            await session.flush()
            staged.append(result.decision_id)
            return result
        monkeypatch.setattr(authority, "consume", observe)
        original_read = TaskRepository.read_audit_task_evidence
        async def broken_read(repo, request):
            assert (await original_read(repo, request)).items
            raise RuntimeError("projection failure after real read")
        original = getattr(TypeAdapter, "dump_json" if failure == "serialization" else "validate_json")
        def broken_response(adapter, value, *args, **kwargs):
            result = original(adapter, value, *args, **kwargs)
            assert result
            raise RuntimeError("response failure")
        if failure == "projection":
            monkeypatch.setattr(TaskRepository, "read_audit_task_evidence", broken_read)
        elif failure != "reference":
            monkeypatch.setattr(TypeAdapter, "dump_json" if failure == "serialization" else "validate_json", broken_response)
        expected = TaskValidationError if failure == "reference" else RuntimeError
        message = "task audit evidence is invalid" if failure == "reference" else "failure"
        with pytest.raises(expected, match=message):
            await command.audit_evidence(AuditTaskEvidenceRequest(project, task))
        assert len(staged) == 1 and not session.in_transaction()
    async with factory() as independent:
        assert await count(independent, actor.actor_profile_id, ACTION) == 0
        assert (await independent.get(WorkstreamTask, str(task))).title == original_title


async def test_audit_write_rollback(admin_access, monkeypatch):
    from sqlalchemy.exc import SQLAlchemyError
    from app.modules.audit.service import AuditService
    from app.modules.authorization.runtime import AuthorizationEvidenceUnavailable
    from app.modules.tasks.models import WorkstreamTask
    from app.modules.tasks.repository import TaskRepository
    from tests.authorization.task_locked_context.test_transactions import count
    project, _, task = await task_case(admin_access)
    await grant_audit(admin_access, project)
    actor = await actor_context(str(admin_access.target.id))
    factory = db_session.get_session_factory()
    async with factory() as initial:
        original_title = (await initial.get(WorkstreamTask, str(task))).title
    attempted = []
    async with factory() as session:
        async def fail_write(*args, **kwargs):
            attempted.append(True)
            row = await session.get(WorkstreamTask, str(task))
            row.title = "failed audit write marker"
            await session.flush()
            raise SQLAlchemyError("audit persistence unavailable")
        async def no_projection(*args, **kwargs):
            raise AssertionError("projection after failed audit write")
        monkeypatch.setattr(AuditService, "add_authority_event", fail_write)
        monkeypatch.setattr(TaskRepository, "read_audit_task_evidence", no_projection)
        command = task_commands(session, settings=get_settings(), authorization=PreparedTaskAuthorization(session, actor),
                               audit=task_transition_audit(session), actor_profile_id=actor.actor_profile_id)
        with pytest.raises(AuthorizationEvidenceUnavailable):
            await command.audit_evidence(AuditTaskEvidenceRequest(project, task))
        assert attempted and not session.in_transaction()
    async with factory() as independent:
        assert await count(independent, actor.actor_profile_id, ACTION) == 0
        assert (await independent.get(WorkstreamTask, str(task))).title == original_title

@pytest.mark.parametrize("first", ("read", "revoke"))
async def test_revocation_serialization(admin_access, auth_database_env, monkeypatch, first):
    project, manager, task = await task_case(admin_access)
    grant = await grant_audit(admin_access, project)
    actor = await actor_context(str(admin_access.target.id))
    admin = await actor_context(str(admin_access.admin.id))
    acquired, proceed = asyncio.Event(), asyncio.Event()
    original = PreparedTaskAuthorization.consume
    async def hold(authority, handle, facts):
        result = await original(authority, handle, facts)
        if first == "read":
            acquired.set()
            await proceed.wait()
        return result
    monkeypatch.setattr(PreparedTaskAuthorization, "consume", hold)
    async def run(operation):
        async with db_session.get_session_factory()() as session:
            await session.execute(text("select set_config('application_name',:name,false)"), {"name":"task-read-" + operation})
            await session.commit()
            if operation == "revoke":
                async with session.begin():
                    await revoke_manager_grant(session, admin, UUID(grant))
                    if first == "revoke":
                        acquired.set()
                        await proceed.wait()
                return "revoked"
            command = task_commands(session, settings=get_settings(), authorization=PreparedTaskAuthorization(session, actor),
                audit=task_transition_audit(session), actor_profile_id=actor.actor_profile_id)
            return await command.audit_evidence(AuditTaskEvidenceRequest(project, task))
    a = asyncio.create_task(run(first))
    b = None
    second = "revoke" if first == "read" else "read"
    try:
        await asyncio.wait_for(acquired.wait(), 20)
        b = asyncio.create_task(run(second))
        await asyncio.wait_for(wait_for_named_database_lock(auth_database_env, "task-read-" + second), 10)
        assert not b.done()
    finally:
        proceed.set()
        results = await asyncio.wait_for(asyncio.gather(*(job for job in (a,b) if job is not None), return_exceptions=True), 20)
    assert len(results) == 2
    if first == "read":
        assert str(results[0].task_id) == str(task) and results[1] == "revoked"
    else:
        assert results[0] == "revoked" and isinstance(results[1], TaskAuthorityDenied)


async def test_wrong_project_does_not_wait(admin_access):
    from app.modules.tasks.models import WorkstreamTask
    from tests.authorization.task_queues.support import project_fixture
    foreign_project, _, task = await task_case(admin_access)
    requested_project = await project_fixture()
    await grant_audit(admin_access,requested_project)
    async with db_session.get_session_factory()() as holder, holder.begin():
        locked = await holder.get(WorkstreamTask,str(task),with_for_update=True)
        assert locked.project_id == str(foreign_project) != str(requested_project)
        response = await asyncio.wait_for(admin_access.signed.client.get(
            path(requested_project,task),headers=admin_access.target.headers,
        ),timeout=10)
        assert response.status_code==404,response.text
        assert response.json()["error"]["code"]=="project_authorization_resource_not_found"


async def test_task_only_lock_probe(admin_access, monkeypatch):
    from app.modules.tasks.repository import TaskRepository
    async def task_only(self, project_id, task_id):
        return await self.get_task(str(task_id), for_update=True)
    monkeypatch.setattr(TaskRepository, "lock_project_task", task_only)
    with pytest.raises(TimeoutError):
        await test_wrong_project_does_not_wait(admin_access)
