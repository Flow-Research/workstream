"""Signed HTTP reads require exact audience grants, not shared permissions."""

from dataclasses import replace

import pytest
from sqlalchemy import select

from app.core.identifiers import new_record_id
from app.db import session as db_session
from app.modules.tasks.models import AuditEvent
from tests.authorization.task_reads.support import task_case
from tests.authorization.task_locked_context.support import KINDS, grant_for, path
from tests.tasks.test_locked_context import REFERENCE_FIELDS, SUMMARY


@pytest.mark.parametrize("kind", KINDS)
async def test_locked_context_exact_role_matrix(admin_access, kind):
    project, _, task = await task_case(admin_access)
    cases = [(role, system) for role in ("project_manager", "audit_authority", "finance_authority") for system in (False,True)]
    cases += [("operator",True),("access_administrator",True),("token_only",False),("foreign",False),("submitter",False)]
    for role, system in cases:
        actor = await admin_access.signed.actor(f"context-{role}-{system}", roles=("project_manager","operator","admin"))
        access = replace(admin_access,target=actor)
        grant = None
        if role == "foreign":
            from tests.authorization.admin_access.support import create_project
            other = await create_project("Foreign context authority")
            grant = await access.signed.grant(access.admin,actor,role="audit_authority" if kind=="audit" else "project_manager",project_id=other)
        elif role == "submitter":
            from tests.authorization.task_queues.support import grant_queue_role
            grant = await grant_queue_role(access, project, "submitter")
        elif role != "token_only":
            grant = await access.signed.grant(access.admin,actor,role=role,project_id=None if system else project)
        allowed = role == KINDS[kind][2]
        response = await access.signed.client.get(path(kind,project,task),headers=actor.headers)
        assert response.status_code == (200 if allowed else 404), (role,system,response.text)
        if allowed:
            assert set(response.json()) == REFERENCE_FIELDS | ({SUMMARY} if kind=="management" else set())
            assert response.json()["task_id"] == str(task)
        else:
            assert response.json()["error"]["code"] == "project_authorization_resource_not_found"
        async with db_session.get_session_factory()() as session:
            events = list(await session.scalars(select(AuditEvent).where(AuditEvent.actor_id==str(actor.id),AuditEvent.action_id==KINDS[kind][1])))
            assert len(events)==1
            event=events[0]
            assert event.project_id == event.resource_id == str(project)
            assert event.after_facts["allowed"] is allowed
            assert event.after_facts["resource_context_digest"].startswith("sha256:")
            assert event.matched_grant_id == (grant if allowed else None)


async def test_audit_dual_role_selects_audit_grant(admin_access):
    project, _, task = await task_case(admin_access)
    manager = await grant_for(admin_access,project,"management")
    audit = await grant_for(admin_access,project,"audit")
    assert manager != audit
    response=await admin_access.signed.client.get(path("audit",project,task),headers=admin_access.target.headers)
    assert response.status_code==200,response.text
    async with db_session.get_session_factory()() as session:
        event=await session.scalar(select(AuditEvent).where(AuditEvent.actor_id==str(admin_access.target.id),AuditEvent.action_id==KINDS["audit"][1]))
        assert event.matched_grant_id == audit


@pytest.mark.parametrize("kind", KINDS)
async def test_locked_context_concealment_and_draft(admin_access, kind):
    project, _, task = await task_case(admin_access)
    await grant_for(admin_access,project,kind)
    client=admin_access.signed.client
    forbidden=await admin_access.signed.actor("no-context-grant")
    responses=[]
    for p,t,actor in ((project,task,forbidden),(project,new_record_id(),admin_access.target),(new_record_id(),task,admin_access.target)):
        response=await client.get(path(kind,p,t),headers=actor.headers)
        assert response.status_code==404,response.text
        responses.append((response.json()["detail"],response.json()["error"]["code"]))
    assert len(set(responses))==1
    malformed=await client.get(path(kind,project,"bad"),headers=admin_access.target.headers)
    assert malformed.status_code==422
    from tests.authorization.task_reads.support import create_task
    from tests.authorization.task_authority.test_postgresql import project_manager
    manager=await project_manager(admin_access,project)
    draft=await create_task(admin_access,project,manager,ready=False)
    response=await client.get(path(kind,project,draft),headers=admin_access.target.headers)
    assert response.status_code==422 and response.json()["code"]=="task_locked_context_invalid"


@pytest.mark.parametrize("kind", KINDS)
async def test_locked_context_revocation_is_live(admin_access,kind):
    from app.modules.actors.models import ActorIdentityLink
    from uuid import uuid4
    project, _, task=await task_case(admin_access)
    for transition in ("grant","link","profile"):
        actor=await admin_access.signed.actor("context-revoke-"+transition)
        access=replace(admin_access,target=actor)
        grant=await grant_for(access,project,kind)
        response=await access.signed.client.get(path(kind,project,task),headers=actor.headers)
        assert response.status_code==200,response.text
        if transition == "grant":
            mutation = await access.signed.revoke(access.admin,grant)
        else:
            url = f"/api/v1/actors/{actor.id}/suspend"
            if transition == "link":
                async with db_session.get_session_factory()() as session:
                    link = await session.scalar(select(ActorIdentityLink).where(ActorIdentityLink.actor_profile_id==str(actor.id)))
                    url = f"/api/v1/actor-identity-links/{link.id}/revoke"
            mutation = await access.signed.client.post(url,headers=access.admin.headers | {"Idempotency-Key":str(uuid4())},json={"reason":"Withdraw locked-context authority"})
        assert mutation.status_code == 200, mutation.text
        response=await access.signed.client.get(path(kind,project,task),headers=actor.headers)
        assert response.status_code==404,response.text


async def test_audit_role_probe_detects_shared_permission_access(admin_access, monkeypatch):
    from app.modules.authorization.repository import AdminAuthorizationRepository
    original = AdminAuthorizationRepository.find_effective_grant
    async def omit_role(self, *args, **kwargs):
        kwargs["allowed_roles"] = None
        return await original(self, *args, **kwargs)
    monkeypatch.setattr(AdminAuthorizationRepository, "find_effective_grant", omit_role)
    with pytest.raises(AssertionError, match="project_manager"):
        await test_locked_context_exact_role_matrix(admin_access, "audit")


@pytest.mark.parametrize("kind", KINDS)
async def test_concealment_probe_detects_omitted_action(admin_access, monkeypatch, kind):
    from app.api.deps import authorization as owner
    from app.modules.authorization.catalogue import ActionId
    monkeypatch.setattr(owner, "TASK_CONCEALED_READ_ACTIONS", owner.TASK_CONCEALED_READ_ACTIONS - {ActionId(KINDS[kind][1])})
    with pytest.raises(AssertionError, match="Task authority denied"):
        await test_locked_context_concealment_and_draft(admin_access, kind)
