"""Signed HTTP reads bind exact stored grants and conceal denied resources."""
from dataclasses import replace

import pytest
from sqlalchemy import select

from app.core.identifiers import new_record_id
from app.db import session as db_session
from app.modules.tasks.models import AuditEvent
from tests.authorization.task_queues.support import grant_queue_role
from tests.authorization.task_reads.support import READS, path, task_case


@pytest.mark.parametrize("kind", READS)
async def test_task_read_authority_matrix(admin_access, kind):
    project, manager, task = await task_case(admin_access)
    for role in ("submitter", "project_manager", "system_manager", "operator", "reviewer", "audit_authority", "finance_authority", "access_administrator", "token_only", "foreign"):
        actor = await admin_access.signed.actor("read-" + role, roles=("project_manager", "worker", "operator") if role == "token_only" else ())
        access = replace(admin_access, target=actor)
        grant_id = None
        if role == "access_administrator":
            actor = admin_access.admin
        elif role == "foreign":
            from tests.authorization.admin_access.support import create_project
            other = await create_project("Other project")
            grant_id = await grant_queue_role(access, other, "project_manager")
        elif role != "token_only":
            grant_id = await grant_queue_role(access, project, role)
        allowed = role in ({"submitter"} if kind.startswith("contributor") else {"project_manager", "system_manager"})
        response = await access.signed.client.get(path(kind, project, task), headers=actor.headers)
        assert response.status_code == (200 if allowed else 404), (role, response.text)
        if allowed:
            assert response.json()["task_id"] == str(task)
            if kind.endswith("detail"):
                assert response.json()["project_id"] == str(project)
                assert "id" not in response.json()
                assert "locked_payment_policy_version" not in response.json()
                if kind.startswith("contributor"):
                    assert "created_by" not in response.json() and "source_ref" not in response.json()
        else:
            assert response.json()["error"]["code"] == "project_authorization_resource_not_found"
        async with db_session.get_session_factory()() as session:
            decisions = list(await session.scalars(select(AuditEvent).where(AuditEvent.actor_id == str(actor.id), AuditEvent.action_id == READS[kind][1])))
            assert len(decisions) == 1
            decision = decisions[0]
            assert decision.project_id == decision.resource_id == str(project)
            assert decision.after_facts["allowed"] is allowed
            assert decision.after_facts["resource_context_digest"].startswith("sha256:")
            assert decision.matched_grant_id == (grant_id if allowed else None)


@pytest.mark.parametrize("kind", READS)
async def test_task_read_concealment_and_selectors(admin_access, kind):
    project, manager, task = await task_case(admin_access)
    paths = [path(kind, project, task), path(kind, project, new_record_id())]
    if kind.startswith("management"):
        paths.append(path(kind, new_record_id(), task))
    values = []
    for url in paths:
        response = await admin_access.signed.client.get(url, headers=admin_access.target.headers)
        assert response.status_code == 404, response.text
        body = response.json()
        values.append((body["detail"], body["error"]["code"], body["error"]["message"]))
    assert len(set(values)) == 1
    invalid = await admin_access.signed.client.get(path(kind, project, "bad-uuid"), headers=manager.headers)
    assert invalid.status_code == 422
    from tests.authentication.support import issue_asymmetric_token
    token = issue_asymmetric_token(admin_access.signed.private_key, scope="workstream:service", claims={"sub":"unprovisioned-task-reader", "subject_kind":"service"})
    rejected = await admin_access.signed.client.get(path(kind, project, task), headers={"Authorization": "Bearer " + token})
    assert rejected.status_code == 404 and rejected.json()["error"]["code"] == values[0][1]


async def test_manager_draft_detail_and_requirements(admin_access):
    project, manager, task = await task_case(admin_access, ready=False)
    detail = await admin_access.signed.client.get(path("management_detail", project, task), headers=manager.headers)
    assert detail.status_code == 200 and detail.json()["status"] == "draft"
    requirements = await admin_access.signed.client.get(path("management_requirements", project, task), headers=manager.headers)
    assert requirements.status_code == 422 and requirements.json()["code"] == "task_locked_context_invalid"
    async with db_session.get_session_factory()() as session:
        assert list(await session.scalars(select(AuditEvent).where(AuditEvent.actor_id == str(manager.id), AuditEvent.action_id == READS["management_requirements"][1]))) == []


@pytest.mark.parametrize("kind", READS)
async def test_task_read_rechecks_live_authority(admin_access, kind):
    from app.modules.actors.models import ActorIdentityLink
    from uuid import uuid4
    project, manager, task = await task_case(admin_access)
    client = admin_access.signed.client
    for transition in ("grant", "profile", "link"):
        actor = await admin_access.signed.actor("revocable-" + transition)
        access = replace(admin_access,target=actor)
        grant = await grant_queue_role(access,project,"submitter" if kind.startswith("contributor") else "project_manager")
        assert (await client.get(path(kind,project,task),headers=actor.headers)).status_code == 200
        if transition == "grant":
            if kind.startswith("contributor"):
                mutation = await client.post(f"/api/v1/projects/{project}/role-grants/{grant}/revoke",headers=manager.headers | {"Idempotency-Key":str(uuid4())},json={"reason":"Withdraw read authority"})
            else:
                mutation = await access.signed.revoke(access.admin,grant)
        else:
            url = f"/api/v1/actors/{actor.id}/suspend"
            if transition == "link":
                async with db_session.get_session_factory()() as session:
                    link = await session.scalar(select(ActorIdentityLink).where(ActorIdentityLink.actor_profile_id == str(actor.id)))
                    url=f"/api/v1/actor-identity-links/{link.id}/revoke"
            mutation=await client.post(url,headers=admin_access.admin.headers | {"Idempotency-Key":str(uuid4())},json={"reason":"Withdraw read identity"})
        assert mutation.status_code == 200, mutation.text
        denied=await client.get(path(kind,project,task),headers=actor.headers)
        assert denied.status_code == 404, (transition,denied.text)
        assert denied.json()["error"]["code"] == "project_authorization_resource_not_found"
        async with db_session.get_session_factory()() as session:
            allowed=list(await session.scalars(select(AuditEvent).where(AuditEvent.actor_id == str(actor.id),AuditEvent.action_id == READS[kind][1],AuditEvent.event_type == "SensitiveAuthorizationAllowed")))
            assert len(allowed)==1 and allowed[0].matched_grant_id==grant
