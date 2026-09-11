"""Real task HTTP transitions; identity tokens do not grant project authority."""

from uuid import uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import OperationalError

from app.db import session as db_session
from app.modules.actors.models import ActorIdentityLink, ActorProfile, LegacyWorkflowEligibility
from app.modules.actors.service import ActorService, IdentityLinkRevoked
from app.modules.authorization.models import AdminRoleGrant, AuthorityControl, ProjectRoleGrant
from app.modules.authorization.runtime import AuthorizationEvidenceUnavailable
from app.modules.authorization.task_authorization import PreparedTaskAuthorization
from app.modules.tasks.api import TaskAuthorityDenied
from app.modules.audit.service import AuditService, LifecycleAuditParticipant
from app.modules.tasks.models import AuditEvent, TaskAssignment, WorkstreamTask
from app.modules.tasks.authorized_commands import AuthorizedTaskCommands
from app.modules.tasks.service import TaskServiceError
from tests.test_tasks import (
    task_database_env as task_database_env,
    task_client as task_client,
    create_active_project,
    create_ready_task,
    create_started_task,
    complete_submission_payload,
    admit_and_grant_project_submitter,
    auth_headers,
    set_dev_actor,
)
from tests.authorization.task_authority.test_lifecycle_races import (
    _read_task_contributor_race_snapshot,
)


@pytest.mark.parametrize("packet", ["complete", "forged_context", "empty"])
async def test_retired_packet_post_cannot_mutate_an_authorized_assignment(
    task_client, task_database_env, monkeypatch, packet,
):
    """Even a current assigned Submitter cannot invoke the retired packet writer."""
    project = await create_active_project(task_client)
    task = await create_started_task(task_client, project["id"], monkeypatch)
    before = await _read_task_contributor_race_snapshot(task_database_env, task["id"])
    payload = complete_submission_payload() if packet != "empty" else {}
    if packet == "forged_context":
        payload.update(contributor_id=str(uuid4()), locked_guide_version="client-controlled")
    response = await task_client.post(
        f"/api/v1/tasks/{task['id']}/submissions", headers=auth_headers(), json=payload,
    )
    assert response.status_code == 405, response.text
    assert "POST" not in response.headers["allow"]
    assert await _read_task_contributor_race_snapshot(task_database_env, task["id"]) == before
    retained_read = await task_client.get(
        f"/api/v1/tasks/{task['id']}/submissions", headers=auth_headers(),
    )
    assert retained_read.status_code == 200, retained_read.text
    assert retained_read.json() == []


async def test_retired_worker_endpoint_cannot_admit_or_self_authorize(task_client, monkeypatch):
    """A removed route is not a hidden activation route, regardless of token roles."""
    models = (ActorProfile, ActorIdentityLink, LegacyWorkflowEligibility, ProjectRoleGrant)
    async with db_session.get_session_factory()() as session:
        before = [await session.scalar(select(func.count()).select_from(model)) for model in models]
    for roles in ("viewer", "worker", "admin"):
        set_dev_actor(monkeypatch, roles=roles, subject=f"retired-route-{roles}")
        response = await task_client.post(
            "/api/v1/workers/me/profile", headers=auth_headers(),
            json={"skills": ["python"], "display_name": "No self-activation"},
        )
        assert response.status_code == 404, response.text
    anonymous = await task_client.post("/api/v1/workers/me/profile", json={})
    assert anonymous.status_code == 404, anonymous.text
    async with db_session.get_session_factory()() as session:
        after = [await session.scalar(select(func.count()).select_from(model)) for model in models]
    assert after == before


async def test_project_grant_drives_claim_start_and_current_action_hints(task_client, monkeypatch):
    project = await create_active_project(task_client)
    task = await create_ready_task(task_client, project["id"])
    task_id = task["id"]
    set_dev_actor(monkeypatch, roles="viewer", subject="explicit-submitter")
    admitted = await task_client.get("/api/v1/actors/me", headers=auth_headers())
    assert admitted.status_code == 200, admitted.text
    actor_id = admitted.json()["actor_profile_id"]
    for method, suffix in (("post", "claim"), ("get", "work-context")):
        denied = await getattr(task_client, method)(
            f"/api/v1/tasks/{task_id}/{suffix}",
            headers=auth_headers(),
        )
        assert denied.status_code == 403, denied.text
        assert denied.json()["error"]["code"] == "permission_not_granted"
        assert denied.json()["error"]["retryable"] is False
        assert denied.json()["error"]["correlation_id"] == denied.headers["x-correlation-id"]
    async with db_session.get_session_factory()() as session:
        untouched = await session.get(WorkstreamTask, task_id)
        assert untouched.status == "ready" and untouched.assigned_to is None
        assert (
            await session.scalar(select(TaskAssignment).where(TaskAssignment.task_id == task_id))
            is None
        )

    authority = await admit_and_grant_project_submitter(
        task_client,
        monkeypatch,
        project["id"],
        "explicit-submitter",
    )
    assert authority["actor_profile_id"] == actor_id
    context = await task_client.get(f"/api/v1/tasks/{task_id}/work-context", headers=auth_headers())
    assert context.status_code == 200, context.text
    assert context.json()["lifecycle"]["next_actions"] == ["claim"]
    claimed = await task_client.post(f"/api/v1/tasks/{task_id}/claim", headers=auth_headers())
    assert claimed.status_code == 200, claimed.text
    assert claimed.json()["assignment"]["contributor_id"] == actor_id
    assert claimed.json()["task"]["status"] == "claimed"
    context = await task_client.get(f"/api/v1/tasks/{task_id}/work-context", headers=auth_headers())
    assert context.status_code == 200, context.text
    assert context.json()["lifecycle"]["next_actions"] == ["start"]
    set_dev_actor(monkeypatch, roles="project_manager", subject="project-manager-subject")
    revoked = await task_client.post(
        f"/api/v1/projects/{project['id']}/role-grants/{authority['grant_id']}/revoke",
        headers=auth_headers(),
        json={"reason": "Withdraw project work authority"},
    )
    assert revoked.status_code == 200, revoked.text
    set_dev_actor(monkeypatch, roles="viewer", subject="explicit-submitter")
    blocked = await task_client.post(f"/api/v1/tasks/{task_id}/start", headers=auth_headers())
    assert blocked.status_code == 403, blocked.text
    async with db_session.get_session_factory()() as session:
        unchanged = await session.get(WorkstreamTask, task_id)
        assert unchanged.status == "claimed" and unchanged.assigned_to == actor_id
        assignment = await session.get(TaskAssignment, claimed.json()["assignment"]["id"])
        assert assignment.status == "active" and assignment.contributor_id == actor_id
    await admit_and_grant_project_submitter(
        task_client, monkeypatch, project["id"], "explicit-submitter"
    )
    started = await task_client.post(f"/api/v1/tasks/{task_id}/start", headers=auth_headers())
    assert started.status_code == 200, started.text
    assert started.json()["status"] == "in_progress"
    context = await task_client.get(f"/api/v1/tasks/{task_id}/work-context", headers=auth_headers())
    assert context.status_code == 200, context.text
    assert context.json()["lifecycle"]["next_actions"] == []
    assert context.json()["lifecycle"]["can_submit"] is False
    assert context.json()["lifecycle"]["can_run_pre_submit_check"] is False

    async with db_session.get_session_factory()() as session:
        assert (
            await session.scalar(
                select(LegacyWorkflowEligibility).where(
                    LegacyWorkflowEligibility.actor_id == actor_id,
                )
            )
            is None
        )
        assignments = list(
            await session.scalars(select(TaskAssignment).where(TaskAssignment.task_id == task_id))
        )
        assert len(assignments) == 1 and assignments[0].contributor_id == actor_id
        transitions = list(
            await session.scalars(
                select(AuditEvent).where(
                    AuditEvent.entity_id == task_id,
                    AuditEvent.to_status.in_(["claimed", "in_progress"]),
                )
            )
        )
        assert {event.to_status for event in transitions} == {"claimed", "in_progress"}
        for event in transitions:
            assert event.actor_id == actor_id
            assert event.actor_roles == [] and event.claim_snapshot == {}
            assert event.event_payload["references"]["authorization_decision_id"]


async def test_task_command_routes_preserve_structured_errors(task_client, monkeypatch):
    """Inject only owner failures; routing must retain request IDs and retry semantics."""
    task_id, project_id = uuid4(), uuid4()
    routes = [
        ("claim", "POST", f"/api/v1/tasks/{task_id}/claim"),
        ("start", "POST", f"/api/v1/tasks/{task_id}/start"),
        ("start", "POST", f"/api/v1/operations/tasks/{task_id}/start"),
        ("work_context", "GET", f"/api/v1/tasks/{task_id}/work-context"),
        ("work_context", "GET", f"/api/v1/projects/{project_id}/tasks/{task_id}/work-context"),
    ]
    for exception, status, code, retryable in [
        (TaskServiceError("bounded task failure"), 400, "invalid_request", False),
        (OperationalError("injected", None, RuntimeError("unavailable")),
         503, "task_authority_unavailable", True),
        (AuthorizationEvidenceUnavailable("injected authority evidence failure"),
         503, "task_authority_unavailable", True),
    ]:
        async def fail(*args, **kwargs):
            raise exception

        for owner_method, method, path in routes:
            with monkeypatch.context() as patch:
                patch.setattr(AuthorizedTaskCommands, owner_method, fail)
                response = await task_client.request(
                    method, path, headers=auth_headers(),
                    **({"json": {"reason": "Explicit operation reason"}} if method == "POST" else {}),
                )
            assert response.status_code == status, response.text
            error = response.json()["error"]
            assert error["code"] == code
            assert error["retryable"] is retryable
            assert error["correlation_id"] == response.headers["x-correlation-id"]


async def test_task_denial_evidence_failure_is_structured_unavailable(task_client, monkeypatch):
    """Unavailable denial evidence must not become a bare 500 or successful denial."""
    async def deny(*args, **kwargs):
        raise TaskAuthorityDenied("injected task denial")

    async def evidence_unavailable(*args, **kwargs):
        raise AuthorizationEvidenceUnavailable("injected denial evidence failure")

    monkeypatch.setattr(AuthorizedTaskCommands, "claim", deny)
    monkeypatch.setattr(PreparedTaskAuthorization, "restage_denial", evidence_unavailable)
    response = await task_client.post(
        f"/api/v1/tasks/{uuid4()}/claim", headers=auth_headers(), json={}
    )
    assert response.status_code == 503, response.text
    error = response.json()["error"]
    assert error["code"] == "task_authority_unavailable"
    assert error["retryable"] is True
    assert error["correlation_id"] == response.headers["x-correlation-id"]


@pytest.mark.parametrize("failure_kind", ["identity_revoked", "database_unavailable"])
async def test_actor_resolution_failure_cannot_reach_task_command(
    task_client, task_database_env, monkeypatch, failure_kind,
):
    """Registry failure rolls back its read transaction before any TASK command."""
    project = await create_active_project(task_client)
    task = await create_ready_task(task_client, project["id"])
    await admit_and_grant_project_submitter(
        task_client, monkeypatch, project["id"], "resolution-failure-submitter"
    )
    before = await _read_task_contributor_race_snapshot(task_database_env, task["id"])
    original = ActorService.find_actor_for_authorization
    resolved_sessions = []
    rollback_observations = []
    command_calls = []

    async def fail_after_lookup(service, token):
        assert await original(service, token) is not None
        assert service._session.in_transaction()
        resolved_sessions.append(service._session)
        rollback = service._session.rollback

        async def observe_rollback():
            was_active = service._session.in_transaction()
            await rollback()
            rollback_observations.append((was_active, service._session.in_transaction()))

        monkeypatch.setattr(service._session, "rollback", observe_rollback)
        if failure_kind == "identity_revoked":
            raise IdentityLinkRevoked("Identity link is revoked")
        raise OperationalError("injected registry failure", None, RuntimeError("unavailable"))

    async def forbidden_command(*args, **kwargs):
        command_calls.append(True)
        raise AssertionError("Actor resolution failure reached TASK")

    monkeypatch.setattr(ActorService, "find_actor_for_authorization", fail_after_lookup)
    monkeypatch.setattr(AuthorizedTaskCommands, "claim", forbidden_command)
    response = await task_client.post(
        f"/api/v1/tasks/{task['id']}/claim", headers=auth_headers(), json={}
    )
    unavailable = failure_kind == "database_unavailable"
    assert response.status_code == (503 if unavailable else 403), response.text
    error = response.json()["error"]
    assert error["code"] == ("service_unavailable" if unavailable else "identity_link_revoked")
    assert error["retryable"] is unavailable
    assert error["correlation_id"] == response.headers["x-correlation-id"]
    assert "injected" not in response.text
    assert len(resolved_sessions) == 1
    assert rollback_observations == [(True, False)]
    assert not resolved_sessions[0].in_transaction()
    assert command_calls == []
    assert await _read_task_contributor_race_snapshot(task_database_env, task["id"]) == before


@pytest.mark.parametrize("failure_phase", ["authority", "transition"])
async def test_claim_rolls_back_and_retries_once_after_evidence_failure(
    task_client, monkeypatch, failure_phase,
):
    project = await create_active_project(task_client)
    task = await create_ready_task(task_client, project["id"])
    await admit_and_grant_project_submitter(
        task_client, monkeypatch, project["id"], "rollback-submitter"
    )
    owner, method = (
        (AuditService, "add_authority_event")
        if failure_phase == "authority"
        else (LifecycleAuditParticipant, "add_event")
    )
    original = getattr(owner, method)
    staged = []

    async def fail_after_flush(participant, value):
        event = await original(participant, value)
        if failure_phase == "authority":
            assert event.action_id == "task.claim"
        staged.append(event.id)
        raise OperationalError("injected audit storage failure", None, RuntimeError("unavailable"))

    headers = auth_headers()
    path = f"/api/v1/tasks/{task['id']}/claim"
    with monkeypatch.context() as patch:
        patch.setattr(owner, method, fail_after_flush)
        response = await task_client.post(path, headers=headers)
    assert response.status_code == 503, response.text
    assert response.json()["error"]["code"] == "task_authority_unavailable"
    assert response.json()["error"]["retryable"] is True
    assert len(staged) == 1
    async with db_session.get_session_factory()() as session:
        unchanged = await session.get(WorkstreamTask, task["id"])
        assert unchanged.status == "ready" and unchanged.assigned_to is None
        assert (
            await session.scalar(select(TaskAssignment).where(TaskAssignment.task_id == task["id"]))
            is None
        )
        assert await session.get(AuditEvent, staged[0]) is None
        assert (
            await session.scalar(select(AuditEvent).where(AuditEvent.action_id == "task.claim"))
            is None
        )

    # Repeat the identical request, including its key, after storage recovers.
    retried = await task_client.post(path, headers=headers)
    assert retried.status_code == 200, retried.text
    assert retried.json()["task"]["status"] == "claimed"
    async with db_session.get_session_factory()() as session:
        assignments = list(await session.scalars(
            select(TaskAssignment).where(TaskAssignment.task_id == task["id"])
        ))
        assert len(assignments) == 1
        assert assignments[0].id == retried.json()["assignment"]["id"]
        assert assignments[0].status == "active"
        claimed = await session.get(WorkstreamTask, task["id"])
        assert claimed.status == "claimed"
        assert claimed.assigned_to == assignments[0].contributor_id
        decisions = list(await session.scalars(
            select(AuditEvent).where(AuditEvent.action_id == "task.claim")
        ))
        transitions = list(await session.scalars(
            select(AuditEvent).where(
                AuditEvent.entity_id == task["id"], AuditEvent.to_status == "claimed",
            )
        ))
        assert len(decisions) == len(transitions) == 1
        decision, transition = decisions[0], transitions[0]
        assert decision.after_facts["allowed"] is True
        assert decision.actor_id == transition.actor_id == assignments[0].contributor_id
        assert decision.project_id == project["id"]
        assert (transition.from_status, transition.to_status) == ("ready", "claimed")
        assert transition.event_payload["references"]["authorization_decision_id"] == decision.id
        assert await session.get(AuditEvent, staged[0]) is None


async def test_manager_context_and_system_operator_override_are_distinct(task_client, monkeypatch):
    project = await create_active_project(task_client)
    task = await create_ready_task(task_client, project["id"])
    task_id = task["id"]
    manager_context = await task_client.get(
        f"/api/v1/projects/{project['id']}/tasks/{task_id}/work-context",
        headers=auth_headers(),
    )
    assert manager_context.status_code == 200, manager_context.text
    assert manager_context.json()["lifecycle"]["next_actions"] == []
    contributor_context = await task_client.get(
        f"/api/v1/tasks/{task_id}/work-context", headers=auth_headers()
    )
    assert contributor_context.status_code == 403, contributor_context.text
    owner = await admit_and_grant_project_submitter(
        task_client, monkeypatch, project["id"], "assigned-contributor"
    )
    claimed = await task_client.post(f"/api/v1/tasks/{task_id}/claim", headers=auth_headers())
    assert claimed.status_code == 200, claimed.text

    set_dev_actor(monkeypatch, roles="project_manager", subject="project-manager-subject")
    denied = await task_client.post(
        f"/api/v1/operations/tasks/{task_id}/start",
        headers=auth_headers(),
        json={"reason": "Manager is not Operator"},
    )
    assert denied.status_code == 403, denied.text
    set_dev_actor(monkeypatch, roles="admin", subject="explicit-operator")
    admitted = await task_client.get("/api/v1/actors/me", headers=auth_headers())
    assert admitted.status_code == 200, admitted.text
    operator_id = admitted.json()["actor_profile_id"]
    denied = await task_client.post(
        f"/api/v1/operations/tasks/{task_id}/start",
        headers=auth_headers(),
        json={"reason": "Token role is not authority"},
    )
    assert denied.status_code == 403, denied.text

    # Use the existing project fixture's bootstrap identity to issue a real
    # Operator grant. This test does not claim to prove bootstrap provisioning.
    async with db_session.get_session_factory()() as session:
        control = await session.get(AuthorityControl, 1)
        bootstrap_grant = await session.get(AdminRoleGrant, control.bootstrap_grant_id)
        bootstrap_link = await session.scalar(
            select(ActorIdentityLink).where(
                ActorIdentityLink.actor_profile_id == bootstrap_grant.target_actor_profile_id,
            )
        )
        bootstrap_subject, bootstrap_issuer = bootstrap_link.subject, bootstrap_link.issuer
    set_dev_actor(monkeypatch, roles="viewer", subject=bootstrap_subject, issuer=bootstrap_issuer)
    issued = await task_client.post(
        "/api/v1/admin-role-grants",
        headers=auth_headers(),
        json={
            "target_actor_profile_id": operator_id,
            "role": "operator",
            "scope_type": "system",
            "scope_project_id": None,
            "reason": "Assign operations responsibility",
        },
    )
    assert issued.status_code == 201, issued.text
    set_dev_actor(monkeypatch, roles="viewer", subject="explicit-operator")
    normal = await task_client.post(f"/api/v1/tasks/{task_id}/start", headers=auth_headers())
    assert normal.status_code == 403, normal.text
    for body in ({}, {"reason": " "}):
        no_reason = await task_client.post(
            f"/api/v1/operations/tasks/{task_id}/start", headers=auth_headers(), json=body
        )
        assert no_reason.status_code == 422, no_reason.text
    reason = "Operator verified assigned contributor started work"
    started = await task_client.post(
        f"/api/v1/operations/tasks/{task_id}/start",
        headers=auth_headers(),
        json={"reason": reason},
    )
    assert started.status_code == 200, started.text
    async with db_session.get_session_factory()() as session:
        row = await session.get(WorkstreamTask, task_id)
        assert row.status == "in_progress" and row.assigned_to == owner["actor_profile_id"]
        assignment = await session.get(TaskAssignment, claimed.json()["assignment"]["id"])
        assert assignment.contributor_id == owner["actor_profile_id"]
        event = await session.scalar(
            select(AuditEvent).where(
                AuditEvent.entity_id == task_id,
                AuditEvent.event_type == "TaskStartOverridden",
            )
        )
        assert event is not None and event.actor_id == operator_id
        assert event.reason == reason
        decision = await session.get(
            AuditEvent, event.event_payload["references"]["authorization_decision_id"]
        )
        assert decision.action_id == "operations.task.start_override"
        assert decision.matched_grant_id == issued.json()["resource_id"]
