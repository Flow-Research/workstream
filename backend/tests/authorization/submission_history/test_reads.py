"""Real HTTP/AUTH/PostgreSQL history reads; retained evidence is a seeded prerequisite."""

from uuid import UUID

import pytest
from sqlalchemy import select

from app.db import session as db_session
from app.core.hashing import canonical_json_hash
from app.modules.tasks.models import AuditEvent, Submission
from app.modules.checkers.models import CheckerRun
from app.modules.authorization.models import ProjectRoleGrant, AdminRoleGrant
from tests.submission_fixtures import seed_retained_submission, seed_retained_checker_run
from tests.test_tasks import (
    create_active_project, create_started_task, complete_submission_payload,
    set_dev_actor, auth_headers, actor_id, admit_and_grant_project_submitter,
)


async def history_case(client, monkeypatch, *, run_status="completed"):
    project = await create_active_project(client)
    task = await create_started_task(client, project["id"], monkeypatch)
    submission = await seed_retained_submission(task["id"], complete_submission_payload())
    run = await seed_retained_checker_run(submission, status=run_status)
    return project["id"], task["id"], submission, run


def history_paths(project, task, submission, run, manager=False):
    prefix = f"/api/v1/projects/{project}" if manager else "/api/v1"
    return {
        "task.submission.list": f"{prefix}/tasks/{task}/submissions",
        "submission.read": f"{prefix}/submissions/{submission}",
        "submission.checker_run.list": f"{prefix}/submissions/{submission}/checker-runs",
        "checker_run.read": f"{prefix}/submissions/{submission}/checker-runs/{run}",
    }


@pytest.mark.parametrize("audience", ["contributor", "system_manager", "project_manager"])
async def test_exact_route_action_and_grant(task_client, monkeypatch, audience):
    manager = audience != "contributor"
    case = await history_case(task_client, monkeypatch)
    project, task, submission, run = case
    subject = "project-manager-subject" if manager else "worker-one"
    if audience == "project_manager":
        from tests.project_create_fixtures import grant_fixture_admin_role
        subject = "scoped-history-manager"
        set_dev_actor(monkeypatch, roles="", subject=subject)
        admission = await task_client.get("/api/v1/actors/me", headers=auth_headers())
        assert admission.status_code == 200, admission.text
        async with db_session.get_session_factory()() as session, session.begin():
            await grant_fixture_admin_role(session, await actor_id(subject), project_id=project)
    set_dev_actor(monkeypatch, roles="", subject=subject)
    who = await actor_id(subject)
    async with db_session.get_session_factory()() as session:
        grant_model = AdminRoleGrant if manager else ProjectRoleGrant
        actor_column = grant_model.target_actor_profile_id if manager else grant_model.actor_profile_id
        query = select(grant_model.id).where(actor_column == who, grant_model.status == "active")
        grant_id = str(await session.scalar(query))
        stored = await session.get(Submission, submission)
        original = {column.name: getattr(stored, column.name) for column in Submission.__table__.columns}
        stored_run = await session.get(CheckerRun, run)
        run_original = {column.name: getattr(stored_run, column.name) for column in CheckerRun.__table__.columns}
        prior_audit = {row.id: {column.name: getattr(row, column.name)
                              for column in AuditEvent.__table__.columns}
                       for row in await session.scalars(select(AuditEvent))}
        assert prior_audit
    for action, path in history_paths(*case, manager=manager).items():
        response = await task_client.get(path, headers=auth_headers())
        assert response.status_code == 200, response.text
        value = response.json()
        item = value["items"][0] if action.endswith("list") else value
        assert item["task_id"] == task
        assert ("contributor_id" in item) is (manager and action in {"task.submission.list", "submission.read"})
        persisted = run_original if "checker" in action else original
        nested = {"results", "evidence_items"}
        for field, returned in item.items():
            if field in nested:
                continue
            stored_value = persisted[field]
            if isinstance(stored_value, UUID):
                assert returned == str(stored_value), field
            elif hasattr(stored_value, "isoformat"):
                assert returned.replace("Z", "+00:00") == stored_value.isoformat()
            else:
                assert returned == stored_value, field
        full_action = ("project." if manager else "") + action
        async with db_session.get_session_factory()() as session:
            event = await session.scalar(select(AuditEvent).where(
                AuditEvent.action_id == full_action, AuditEvent.actor_id == who,
            ))
            assert event is not None and event.after_facts["allowed"] is True
            assert str(event.matched_grant_id) == grant_id
            assert event.project_id == project
            assert event.resource_type == "project" and event.resource_id == project
            resource_id = {"task.submission.list": task, "submission.read": submission,
                           "submission.checker_run.list": submission, "checker_run.read": run}[action]
            resource_type = ("task_submission_history" if action == "task.submission.list" else
                             "checker_history" if action == "checker_run.read" else "submission_history")
            assert event.after_facts["resource_context_digest"] == canonical_json_hash({"resource_context": {
                "resource_type": resource_type, "resource_id": resource_id,
                "scope_project_id": project, "task_id": task, "submission_id": submission,
                "contributor_id": original["contributor_id"], "actor_profile_id": who,
                "request_digest": canonical_json_hash({"action": full_action, "limit": 25, "cursor": None}),
            }})
    async with db_session.get_session_factory()() as session:
        stored = await session.get(Submission, submission)
        assert {column.name: getattr(stored, column.name) for column in Submission.__table__.columns} == original
        for event_id, original_facts in prior_audit.items():
            event = await session.get(AuditEvent, event_id)
            assert {column.name: getattr(event, column.name) for column in AuditEvent.__table__.columns} == original_facts


async def test_list_requires_owned_history(task_client, monkeypatch):
    case = await history_case(task_client, monkeypatch)
    own_paths = history_paths(*case)
    for path in own_paths.values():
        assert (await task_client.get(path, headers=auth_headers())).status_code == 200
    await admit_and_grant_project_submitter(task_client, monkeypatch, case[0], "foreign-history-owner")
    for path in own_paths.values():
        response = await task_client.get(path, headers=auth_headers())
        assert response.status_code == 404, response.text
    who = await actor_id("foreign-history-owner")
    async with db_session.get_session_factory()() as session:
        events = list(await session.scalars(select(AuditEvent).where(
            AuditEvent.actor_id == who, AuditEvent.action_id.in_(tuple(own_paths)),
        )))
        assert events == []  # Foreign ownership is concealed before locking/AUTH.


async def test_management_does_not_infer_authority_from_other_roles(task_client, monkeypatch):
    from tests.project_create_fixtures import grant_fixture_admin_role
    case = await history_case(task_client, monkeypatch)
    for role in ("operator", "audit_authority", "access_administrator", "token_only"):
        subject = "history-role-" + role
        set_dev_actor(monkeypatch, roles="admin,project_manager", subject=subject)
        admission = await task_client.get("/api/v1/actors/me", headers=auth_headers())
        assert admission.status_code == 200, admission.text
        who = await actor_id(subject)
        if role != "token_only":
            async with db_session.get_session_factory()() as session, session.begin():
                await grant_fixture_admin_role(session, who, role=role, scope="system")
        for path in history_paths(*case, manager=True).values():
            response = await task_client.get(path, headers=auth_headers())
            assert response.status_code == 404, (role, response.text)
        async with db_session.get_session_factory()() as session:
            decisions = list(await session.scalars(select(AuditEvent).where(
                AuditEvent.actor_id == who, AuditEvent.action_id.in_(
                    tuple("project." + action for action in history_paths(*case)),
                ),
            )))
            assert len(decisions) == 4
            assert all(not event.after_facts["allowed"] and event.matched_grant_id is None for event in decisions)


@pytest.mark.parametrize("subject_kind", ["service", "agent"])
async def test_nonhuman_tokens_cannot_enter_history(signed_access, monkeypatch, subject_kind):
    from app.core.identifiers import new_record_id
    from app.modules.tasks.submission_history import SubmissionHistoryRepository
    from app.modules.checkers.history import CheckerHistoryRepository
    from tests.authentication.support import issue_asymmetric_token
    token = issue_asymmetric_token(signed_access.private_key, scope="workstream:service", claims={
        "sub": "history-nonhuman", "subject_kind": subject_kind, "roles": ["project_manager", "worker"],
    })
    async def forbidden(*args, **kwargs):
        pytest.fail("nonhuman history request reached an owner")
    monkeypatch.setattr(SubmissionHistoryRepository, "resolve_submission", forbidden)
    monkeypatch.setattr(SubmissionHistoryRepository, "resolve_task_history", forbidden)
    monkeypatch.setattr(CheckerHistoryRepository, "read", forbidden)
    ids = [str(new_record_id()) for _ in range(4)]
    for manager in (False, True):
        for path in history_paths(*ids, manager=manager).values():
            response = await signed_access.client.get(path, headers={"Authorization": f"Bearer {token}"})
            assert response.status_code == 404, response.text
