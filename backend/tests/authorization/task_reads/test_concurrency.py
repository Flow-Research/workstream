"""Reads use the established TASK-first ordering with real authority locks."""
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
from tests.auth_concurrency_support import wait_for_named_database_lock
from tests.authorization.guide_activation.pg_support import revoke_manager_grant
from tests.authorization.task_authority.test_concurrency import actor_context
from tests.authorization.task_queues.support import grant_queue_role
from tests.authorization.task_reads.support import path, task_case


@pytest.mark.parametrize("kind", ("management_detail", "management_requirements"))
@pytest.mark.parametrize("first", ("read", "revoke"))
async def test_task_read_serializes_with_real_revocation(admin_access, auth_database_env, monkeypatch, kind, first):
    project, manager, task = await task_case(admin_access)
    grant = await grant_queue_role(admin_access, project, "project_manager")
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
            return await getattr(command, kind)(project, task)
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


@pytest.mark.parametrize("kind", ("contributor_detail", "contributor_requirements", "management_detail", "management_requirements"))
async def test_task_read_lock_order_and_refresh(admin_access, auth_database_env, monkeypatch, kind):
    from app.modules.tasks.models import WorkstreamTask
    from app.modules.tasks.repository import TaskRepository
    from app.modules.authorization.repository import AdminAuthorizationRepository
    from app.modules.authorization.catalogue import ActionId
    project, manager, task = await task_case(admin_access)
    await grant_queue_role(admin_access, project, "submitter" if kind.startswith("contributor") else "project_manager")
    actor = await actor_context(str(admin_access.target.id))
    factory = db_session.get_session_factory()
    order, facts_seen = [], []
    for owner,method,label in ((TaskRepository,"get_task","task"),(TaskRepository,"lock_project_task","task"),
                              (TaskRepository,"get_active_assignment","assignment"),
                              (AdminAuthorizationRepository,"lock_request_actor","actor"),
                              (AdminAuthorizationRepository,"find_active_project_role","grant"),
                              (AdminAuthorizationRepository,"find_effective_grant","grant")):
        original = getattr(owner,method)
        async def trace(self,*args,_original=original,_label=label,**kwargs):
            order.append(_label)
            return await _original(self,*args,**kwargs)
        monkeypatch.setattr(owner,method,trace)
    original_prepare = PreparedTaskAuthorization.prepare
    async def capture(self,facts):
        facts_seen.append(facts)
        return await original_prepare(self,facts)
    monkeypatch.setattr(PreparedTaskAuthorization,"prepare",capture)
    async with factory() as reader, factory() as writer:
        stale = await reader.get(WorkstreamTask,str(task))
        assert stale.status == "ready"
        await reader.commit()
        await reader.execute(text("select set_config('application_name','task-read-refresh',false)"))
        await reader.commit()
        changed = await writer.get(WorkstreamTask,str(task),with_for_update=True)
        # Title is a display change; the same row lock protects the authority facts.
        changed.title = "Refreshed instructions"
        await writer.flush()
        command = task_commands(reader,settings=get_settings(),authorization=PreparedTaskAuthorization(reader,actor),
            audit=task_transition_audit(reader),actor_profile_id=actor.actor_profile_id)
        async def read():
            return await getattr(command,kind)(*((project,task) if kind.startswith("management") else (task,)))
        waiting=asyncio.create_task(read())
        try:
            await asyncio.wait_for(wait_for_named_database_lock(auth_database_env,"task-read-refresh"),10)
            assert not waiting.done()
        finally:
            await writer.commit()
        result = await asyncio.wait_for(waiting,20)
        assert stale.title == "Refreshed instructions"
        if kind.endswith("detail"):
            assert result.title == stale.title
    assert order[:4] == ["task","assignment","actor","grant"], order
    assert len(facts_seen) == 1 and ActionId(facts_seen[0].operation.value).value.endswith("read")


@pytest.mark.parametrize("kind", ("management_detail", "management_requirements", "management_work_context"))
async def test_wrong_project_read_does_not_wait_on_foreign_task(admin_access, kind):
    from app.modules.tasks.models import WorkstreamTask
    from tests.authorization.task_queues.support import project_fixture
    from tests.authorization.task_authority.test_postgresql import project_manager

    foreign_project, _, task = await task_case(admin_access)
    requested_project = await project_fixture()
    manager = await project_manager(admin_access, requested_project)
    url = (f"/api/v1/projects/{requested_project}/tasks/{task}/work-context"
           if kind == "management_work_context" else path(kind, requested_project, task))
    async with db_session.get_session_factory()() as holder:
        async with holder.begin():
            locked = await holder.get(WorkstreamTask, str(task), with_for_update=True)
            assert locked.project_id == str(foreign_project)
            assert foreign_project != requested_project
            # The foreign row stays locked until after the HTTP response. A
            # task-only SELECT FOR UPDATE cannot finish inside this boundary.
            response = await asyncio.wait_for(
                admin_access.signed.client.get(url, headers=manager.headers), timeout=10,
            )
            assert response.status_code == 404, response.text
            expected_code = ("resource_not_found" if kind == "management_work_context"
                             else "project_authorization_resource_not_found")
            assert response.json()["error"]["code"] == expected_code
