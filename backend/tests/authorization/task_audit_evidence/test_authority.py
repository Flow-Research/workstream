"""Only current covered Audit Authority may inspect any page of task history."""
import json
from dataclasses import replace
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.core.identifiers import new_record_id
from app.db import session as db_session
from app.modules.tasks.models import AuditEvent
from tests.authorization.task_reads.support import task_case
from tests.authorization.task_audit_evidence.support import ACTION, FIELDS, grant_audit, path


async def test_exact_role_matrix(admin_access):
    project, creator, task = await task_case(admin_access)
    cases = [(role, system) for role in ("project_manager", "audit_authority", "finance_authority") for system in (False, True)]
    cases += [("operator", True), ("access_administrator", True), ("token_only", False), ("foreign", False), ("submitter", False)]
    for role, system in cases:
        actor = await admin_access.signed.actor(f"evidence-{role}-{system}", roles=("admin", "project_manager", "auditor"))
        access = replace(admin_access, target=actor)
        grant = None
        if role == "foreign":
            from tests.authorization.admin_access.support import create_project
            foreign = await create_project("Other evidence project")
            grant = await access.signed.grant(access.admin, actor, role="audit_authority", project_id=foreign)
        elif role == "submitter":
            from tests.authorization.task_queues.support import grant_queue_role
            grant = await grant_queue_role(access, project, "submitter")
        elif role != "token_only":
            grant = await access.signed.grant(access.admin, actor, role=role, project_id=None if system else project)
        allowed = role == "audit_authority"
        response = await access.signed.client.get(path(project, task), headers=actor.headers)
        assert response.status_code == (200 if allowed else 404), (role, system, response.text)
        if allowed:
            assert response.json()["project_id"] == str(project)
            assert response.json()["task_id"] == str(task)
            assert response.json()["items"] and all(set(item) == FIELDS for item in response.json()["items"])
        else:
            assert response.json()["error"]["code"] == "project_authorization_resource_not_found"
        async with db_session.get_session_factory()() as session:
            events = list(await session.scalars(select(AuditEvent).where(AuditEvent.actor_id == str(actor.id), AuditEvent.action_id == ACTION)))
            assert len(events) == 1
            event = events[0]
            assert event.resource_id == event.project_id == str(project)
            assert event.after_facts["allowed"] is allowed
            assert event.matched_grant_id == (grant if allowed else None)
    assert (await admin_access.signed.client.get(path(project, task), headers=creator.headers)).status_code == 404


async def test_dual_role_grant_identity(admin_access):
    project, _, task = await task_case(admin_access)
    manager = await admin_access.signed.grant(admin_access.admin, admin_access.target, role="project_manager", project_id=project)
    audit = await grant_audit(admin_access, project)
    assert manager != audit
    response = await admin_access.signed.client.get(path(project, task), headers=admin_access.target.headers)
    assert response.status_code == 200, response.text
    async with db_session.get_session_factory()() as session:
        event = await session.scalar(select(AuditEvent).where(AuditEvent.actor_id == str(admin_access.target.id), AuditEvent.action_id == ACTION))
        assert event.matched_grant_id == audit


async def test_continuation_rechecks_authority(admin_access):
    from app.modules.actors.models import ActorIdentityLink
    project, _, task = await task_case(admin_access)
    for transition in ("grant", "link", "profile"):
        actor = await admin_access.signed.actor("evidence-revoke-" + transition)
        access = replace(admin_access, target=actor)
        grant = await grant_audit(access, project)
        response = await access.signed.client.get(path(project, task), headers=actor.headers, params={"limit": 1})
        assert response.status_code == 200 and response.json()["next_cursor"], response.text
        cursor = json.dumps(response.json()["next_cursor"])
        if transition == "grant":
            mutation = await access.signed.revoke(access.admin, grant)
        else:
            url = f"/api/v1/actors/{actor.id}/suspend"
            if transition == "link":
                async with db_session.get_session_factory()() as session:
                    link = await session.scalar(select(ActorIdentityLink).where(ActorIdentityLink.actor_profile_id == str(actor.id)))
                    url = f"/api/v1/actor-identity-links/{link.id}/revoke"
            mutation = await access.signed.client.post(url, headers=access.admin.headers | {"Idempotency-Key": str(uuid4())}, json={"reason": "Withdraw evidence access"})
        assert mutation.status_code == 200, mutation.text
        response = await access.signed.client.get(path(project, task), headers=actor.headers, params={"limit": 1, "cursor": cursor})
        assert response.status_code == 404, response.text


async def test_concealment(admin_access):
    project, _, task = await task_case(admin_access)
    await grant_audit(admin_access, project)
    denied = await admin_access.signed.actor("evidence-denied")
    responses = []
    for p, t, actor in ((project, task, denied), (project, new_record_id(), admin_access.target), (new_record_id(), task, admin_access.target)):
        response = await admin_access.signed.client.get(path(p, t), headers=actor.headers)
        assert response.status_code == 404
        responses.append((response.json()["detail"], response.json()["error"]["code"]))
    assert len(set(responses)) == 1


async def test_role_filter_probe(admin_access, monkeypatch):
    from app.modules.authorization.repository import AdminAuthorizationRepository
    original = AdminAuthorizationRepository.find_effective_grant
    async def omit_role(self, *args, **kwargs):
        kwargs["allowed_roles"] = None
        return await original(self, *args, **kwargs)
    monkeypatch.setattr(AdminAuthorizationRepository, "find_effective_grant", omit_role)
    with pytest.raises(AssertionError, match="project_manager"):
        await test_exact_role_matrix(admin_access)
