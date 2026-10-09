"""Signed HTTP authority matrices and concealed project queue access."""

from uuid import uuid4
from app.core.identifiers import new_record_id

import pytest
from sqlalchemy import select, update

from app.db import session as db_session
from app.modules.tasks.models import AuditEvent
from app.modules.projects.models import Project
from tests.authorization.task_queues.support import ACTIONS, PATHS, grant_queue_role, project_fixture


@pytest.mark.parametrize("kind", PATHS)
async def test_queue_authority_matrix(admin_access, kind):
    from dataclasses import replace
    project = await project_fixture()
    for role in ("submitter", "reviewer", "project_manager", "system_manager", "operator", "token_only", "access_administrator", "foreign"):
        target = await admin_access.signed.actor("matrix-" + role)
        await assert_queue_authority(replace(admin_access, target=target), project, kind, role)


async def assert_queue_authority(access, project, kind, role):
    actor = access.target
    grant_id = None
    if role == "access_administrator":
        actor = access.admin
    elif role == "token_only":
        actor = await access.signed.actor("claim-only", roles=("project_manager", "operator", "worker"))
    elif role == "foreign":
        other = await project_fixture("Foreign")
        await grant_queue_role(access, other, "submitter" if kind == "ready" else "project_manager")
    else:
        grant_id = await grant_queue_role(access, project, role)
    response = await access.signed.client.get(PATHS[kind].format(project=project), headers=actor.headers)
    allowed = role in {
        "ready": {"submitter", "reviewer"}, "management": {"project_manager", "system_manager"},
        "operational": {"operator"},
    }[kind]
    assert response.status_code == (200 if allowed else 404), response.text
    if allowed:
        assert response.json() == {"project_id": str(project), "items": [], "next_cursor": None}
    async with db_session.get_session_factory()() as session:
        decisions = list(await session.scalars(select(AuditEvent).where(
            AuditEvent.actor_id == str(actor.id), AuditEvent.action_id == ACTIONS[kind],
        )))
        assert len(decisions) == 1
        decision = decisions[0]
        assert decision.project_id == decision.resource_id == str(project)
        assert decision.after_facts["allowed"] is allowed
        assert decision.after_facts["resource_context_digest"].startswith("sha256:")
        if allowed:
            assert grant_id is not None
            assert decision.matched_grant_id == grant_id
        else:
            assert decision.matched_grant_id is None


@pytest.mark.parametrize("kind", PATHS)
async def test_queue_conceals_absent_and_unauthorized_projects(admin_access, kind):
    from tests.authorization.admin_access.support import create_project
    project = await create_project("Concealed")
    replies = []
    for target in (project, new_record_id()):
        response = await admin_access.signed.client.get(
            PATHS[kind].format(project=target), headers=admin_access.target.headers,
        )
        assert response.status_code == 404
        body = response.json()
        replies.append((body["detail"], body["error"]["code"], body["error"]["message"]))
    assert replies[0] == replies[1]


@pytest.mark.parametrize("kind", PATHS)
async def test_queue_project_lifecycle(admin_access, kind):
    project = await project_fixture()
    await grant_queue_role(admin_access, project, {
        "ready": "submitter", "management": "project_manager", "operational": "operator",
    }[kind])
    for status in ("active", "paused", "archived", "draft"):
        async with db_session.get_session_factory()() as session, session.begin():
            await session.execute(update(Project).where(Project.id == str(project)).values(status=status))
        response = await admin_access.signed.client.get(
            PATHS[kind].format(project=project), headers=admin_access.target.headers,
        )
        assert response.status_code == (404 if kind == "ready" and status != "active" else 200), (status, response.text)


@pytest.mark.parametrize("kind", PATHS)
async def test_queue_revalidates_grant(admin_access, kind, monkeypatch):
    project = await project_fixture()
    grant_id = await grant_queue_role(admin_access, project, {
        "ready": "submitter", "management": "project_manager", "operational": "operator",
    }[kind])
    client, actor = admin_access.signed.client, admin_access.target
    path = PATHS[kind].format(project=project)
    assert (await client.get(path, headers=actor.headers)).status_code == 200
    # A verified position need not name a still-present row; it remains no authority.
    from datetime import UTC, datetime
    from app.core.config import get_settings
    from app.modules.authorization.api.task_queues import TaskQueueReadRequest, TaskQueuePosition
    from app.modules.authorization.task_queue_read import TaskQueueReadAuthorization
    cursor = TaskQueueReadAuthorization(None, get_settings().pagination_cursor_hmac_secret).encode(
        TaskQueueReadRequest(ACTIONS[kind], project, 50, None),
        TaskQueuePosition(datetime.now(UTC), new_record_id()),
    )
    assert (await client.get(path, params={"cursor": cursor}, headers=actor.headers)).status_code == 200
    if kind == "ready":
        from tests.authorization.task_authority.test_postgresql import project_manager
        manager = await project_manager(admin_access, project)
        revoked = await client.post(
            f"/api/v1/projects/{project}/role-grants/{grant_id}/revoke",
            headers=manager.headers | {"Idempotency-Key": str(uuid4())},
            json={"reason": "Withdraw queue authority"},
        )
    else:
        revoked = await admin_access.signed.revoke(admin_access.admin, grant_id)
    assert revoked.status_code == 200, revoked.text
    from app.modules.tasks.repository import TaskRepository

    async def unexpected_read(*args, **kwargs):
        pytest.fail("denied authority must not reach TASK")

    for method in ("read_ready_tasks", "read_management_tasks", "read_operational_tasks"):
        monkeypatch.setattr(TaskRepository, method, unexpected_read)
    for params in ({}, {"cursor": cursor}, {"cursor": "malformed"}):
        denied = await client.get(path, params=params, headers=actor.headers)
        assert denied.status_code == 404, denied.text


@pytest.mark.parametrize("kind", PATHS)
@pytest.mark.parametrize("transition", ["profile", "link"])
async def test_queue_rejects_inactive_identity(admin_access, kind, transition):
    from app.modules.actors.models import ActorIdentityLink

    project = await project_fixture()
    await grant_queue_role(admin_access, project, {
        "ready": "submitter", "management": "project_manager", "operational": "operator",
    }[kind])
    client, actor = admin_access.signed.client, admin_access.target
    path = PATHS[kind].format(project=project)
    assert (await client.get(path, headers=actor.headers)).status_code == 200
    if transition == "profile":
        mutation = f"/api/v1/actors/{actor.id}/suspend"
    else:
        async with db_session.get_session_factory()() as session:
            link = await session.scalar(select(ActorIdentityLink).where(ActorIdentityLink.actor_profile_id == str(actor.id)))
            mutation = f"/api/v1/actor-identity-links/{link.id}/revoke"
    response = await client.post(mutation, headers=admin_access.admin.headers | {"Idempotency-Key": str(uuid4())}, json={"reason": "Withdraw request identity"})
    assert response.status_code == 200, response.text
    denied = await client.get(path, headers=actor.headers)
    assert denied.status_code == 404, denied.text
    async with db_session.get_session_factory()() as session:
        allowed = list(await session.scalars(select(AuditEvent).where(
            AuditEvent.actor_id == str(actor.id), AuditEvent.action_id == ACTIONS[kind],
            AuditEvent.event_type == "SensitiveAuthorizationAllowed",
        )))
        assert len(allowed) == 1


@pytest.mark.parametrize("kind", PATHS)
async def test_queue_conceals_service_actor_before_product_read(signed_access, kind):
    from tests.authentication.support import issue_asymmetric_token
    token = issue_asymmetric_token(signed_access.private_key, scope="workstream:service", claims={
        "sub": "unprovisioned-queue-service", "subject_kind": "service", "roles": ["operator", "project_manager"],
    })
    response = await signed_access.client.get(PATHS[kind].format(project=new_record_id()), headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 404, response.text
    from app.modules.actors.models import ActorIdentityLink
    async with db_session.get_session_factory()() as session:
        assert await session.scalar(select(ActorIdentityLink).where(
            ActorIdentityLink.subject == "unprovisioned-queue-service",
        )) is None


@pytest.mark.parametrize("kind,role", [("management", "system_manager"), ("operational", "operator")])
async def test_granted_queue_reader_conceals_missing_project(admin_access, kind, role):
    await grant_queue_role(admin_access, new_record_id(), role)
    response = await admin_access.signed.client.get(PATHS[kind].format(project=new_record_id()), headers=admin_access.target.headers)
    assert response.status_code == 404, response.text
