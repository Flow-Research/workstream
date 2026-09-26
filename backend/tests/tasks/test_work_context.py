"""Current work-context contracts and real authorized PostgreSQL projections."""

from dataclasses import FrozenInstanceError, asdict, replace
from datetime import UTC, datetime
from decimal import Decimal
import re
from unittest.mock import MagicMock
from uuid import UUID
from app.core.identifiers import new_record_id

import pytest
from pydantic import ValidationError
from sqlalchemy import select

from app.db import session as db_session
from app.main import create_app
from app.modules.projects.api.guide_activation import GuidePolicySelection
from app.modules.projects.api.locked_policy import GuideDisplayFacts, ProjectDisplayFacts
from app.modules.tasks.api import ContributorTaskDetail, ManagementTaskDetail
from app.modules.tasks.schemas import (
    ContributorTaskLifecycle, ContributorTaskWorkContext, ManagementTaskWorkContext,
)
from app.modules.tasks.authorized_commands import AuthorizedTaskCommands
from app.modules.tasks.lifecycle import ALLOWED_TASK_TRANSITIONS
from app.modules.tasks.models import AuditEvent, TaskAssignment, TaskCommandReceipt, WorkstreamTask
from app.modules.tasks.repository import TaskRepository
from app.modules.tasks.service import TaskService, TaskValidationError
from app.modules.tasks import schemas
from tests.test_tasks import (
    task_database_env as task_database_env, task_client as task_client,
    create_active_project, create_ready_task, create_draft_task, create_started_task,
    admit_and_grant_project_submitter, set_dev_actor, auth_headers,
)

COMMON = {"task_id", "project_id", "title", "description", "task_type", "difficulty", "skill_tags",
          "estimated_time_minutes", "status", "acceptance_criteria", "rejection_criteria",
          "deadline_at", "created_at", "updated_at"}
MANAGEMENT = {"source_type", "source_ref", "source_payload_hash", "import_batch_id", "external_task_id",
              "created_by", "assigned_to"}
CONTEXT = {"task", "project", "guide", "review_policy", "revision_policy", "contribution_policy_version_id"}
ACTIONS = ("task.work_context.read", "project.task.work_context.read")


def context_values():
    project_id, now = new_record_id(), datetime.now(UTC)
    task = ContributorTaskDetail(new_record_id(), project_id, "Title", "Work", None, None, ("tag",), None,
                                 "claimed", None, None, None, now, now)
    selection = GuidePolicySelection(policy_id=new_record_id(), generation=1, policy_hash="sha256:" + "1" * 64)
    values = dict(project=ProjectDisplayFacts(project_id, "Project", "project", None),
                  guide=GuideDisplayFacts(new_record_id(), project_id, "guide", None, now),
                  review_policy=selection, revision_policy=selection, contribution_policy_version_id=new_record_id())
    manager = ManagementTaskDetail(**asdict(task), source_type="manual", source_ref="private",
                                   source_payload_hash=None, import_batch_id=None, external_task_id=None,
                                   created_by="creator", assigned_to="owner")
    return task, manager, values


def test_work_context_contracts():
    task, manager, values = context_values()
    lifecycle = ContributorTaskLifecycle(assigned_to_current_actor=True, next_actions=("start",))
    for cls, detail, extra in (
        (ContributorTaskWorkContext, task, {"lifecycle": lifecycle}),
        (ManagementTaskWorkContext, manager, {}),
    ):
        result = cls(task=detail, **values, **extra)
        assert type(result.task) is type(detail)
        assert not hasattr(result.task, "_sa_instance_state")
        with pytest.raises(ValidationError, match="frozen"):
            result.contribution_policy_version_id = new_record_id()
        with pytest.raises(FrozenInstanceError):
            result.task.title = "changed"
        for replacement in (
            {"task": manager if detail is task else task},
            {"task": replace(detail, project_id=new_record_id())},
            {"project": replace(values["project"], id=new_record_id())},
            {"guide": replace(values["guide"], project_id=new_record_id())},
            {"contribution_policy_version_id": "invalid"},
        ):
            with pytest.raises(ValidationError):
                cls(**(dict(task=detail, **values, **extra) | replacement))
        for kind in ("review_policy", "revision_policy"):
            for field, invalid in (("policy_id", "invalid"), ("generation", 0), ("policy_hash", "invalid")):
                with pytest.raises(ValidationError):
                    cls(**(dict(task=detail, **values, **extra) | {
                        kind: values[kind].model_dump() | {field: invalid},
                    }))
        subclass = type("UnexpectedTaskDetail", (type(detail),), {})
        with pytest.raises(ValidationError, match="work context task is invalid"):
            cls(task=subclass(**asdict(detail)), **values, **extra)
        with pytest.raises(ValidationError, match="extra_forbidden"):
            cls(task=detail, **values, **extra, base_amount=25)
    for extra in ({"next_actions": ("submit",)}, {"next_actions": ("claim", "start")},
                  {"assigned_to_current_actor": []}, {"can_submit": True}, {"status": "claimed"}):
        with pytest.raises(ValidationError):
            ContributorTaskLifecycle(**(lifecycle.model_dump() | extra))
    with pytest.raises(ValidationError, match="frozen"):
        lifecycle.next_actions = ()
    with pytest.raises(ValidationError, match="extra_forbidden"):
        ManagementTaskWorkContext(task=manager, **values, lifecycle=lifecycle)


def test_work_context_openapi():
    schema = create_app().openapi()
    definitions = schema["components"]["schemas"]
    for route, name, fields, action in (
        ("/api/v1/tasks/{task_id}/work-context", "ContributorTaskWorkContext", CONTEXT | {"lifecycle"}, ACTIONS[0]),
        ("/api/v1/projects/{project_id}/tasks/{task_id}/work-context", "ManagementTaskWorkContext", CONTEXT, ACTIONS[1]),
    ):
        operation = schema["paths"][route]["get"]
        assert operation["x-workstream-action-id"] == action
        assert operation["responses"]["200"]["content"]["application/json"]["schema"] == {"$ref": f"#/components/schemas/{name}"}
        assert set(definitions[name]["properties"]) == fields
        assert definitions[name]["additionalProperties"] is False
    assert set(definitions["ContributorTaskDetail"]["properties"]) == COMMON
    assert set(definitions["ManagementTaskDetail"]["properties"]) == COMMON | MANAGEMENT
    assert set(definitions["ContributorTaskLifecycle"]["properties"]) == {"assigned_to_current_actor", "next_actions"}
    assert set(definitions["GuidePolicySelection"]["properties"]) == {"policy_id", "generation", "policy_hash"}
    assert definitions["ContributorTaskWorkContext"]["properties"]["contribution_policy_version_id"]["format"] == "uuid"
    assert "TaskWorkContextResponse" not in definitions


async def test_work_context_invalid_selectors():
    session, authority = MagicMock(), MagicMock()
    commands = AuthorizedTaskCommands(session, authorization=authority, audit=MagicMock(),
                                      actor_profile_id=new_record_id(), contexts=MagicMock())
    for invalid in (None, "not-a-uuid", str(new_record_id()), []):
        with pytest.raises(TaskValidationError):
            await commands.contributor_work_context(invalid)
        for args in ((invalid, new_record_id()), (new_record_id(), invalid)):
            with pytest.raises(TaskValidationError):
                await commands.management_work_context(*args)
    session.begin.assert_not_called()
    session.execute.assert_not_called()
    authority.prepare.assert_not_called()


async def decisions(session, task_id):
    project_id = await session.scalar(select(WorkstreamTask.project_id).where(WorkstreamTask.id == task_id))
    return list(await session.scalars(select(AuditEvent).where(
        AuditEvent.project_id == project_id, AuditEvent.resource_type == "project",
        AuditEvent.resource_id == project_id, AuditEvent.action_id.in_(ACTIONS),
    )))


async def snapshot(factory, task_id):
    async with factory() as session:
        state = []
        for model, predicate in (
            (WorkstreamTask, WorkstreamTask.id == task_id),
            (TaskAssignment, TaskAssignment.task_id == task_id),
            (TaskCommandReceipt, TaskCommandReceipt.task_id == task_id),
            (AuditEvent, (AuditEvent.entity_type == "task") & (AuditEvent.entity_id == task_id)),
        ):
            rows = (await session.execute(select(*model.__table__.c).where(predicate).order_by(model.id))).mappings().all()
            state.append([dict(row) for row in rows])
        return state, {event.id for event in await decisions(session, task_id)}


async def test_work_context_public_projections(task_client, monkeypatch):
    project = await create_active_project(task_client)
    task = await create_ready_task(task_client, project["id"])
    grant = await admit_and_grant_project_submitter(task_client, monkeypatch, project["id"], "context-owner")
    claimed = await task_client.post(f"/api/v1/tasks/{task['id']}/claim", headers=auth_headers())
    assert claimed.status_code == 200, claimed.text
    factory = db_session.get_session_factory()
    async with factory() as session, session.begin():
        row = await session.get(WorkstreamTask, task["id"])
        row.base_amount, row.currency, row.payout_type = Decimal("125.00"), "USD", "flat"
        row.source_ref = row.source_payload_hash = row.import_batch_id = row.external_task_id = "PRIVATE"
        row.deadline_at = datetime(2030, 1, 1, tzinfo=UTC)
    for management in (True, False):
        set_dev_actor(monkeypatch, roles="project_manager" if management else "viewer",
                      subject="project-manager-subject" if management else "context-owner")
        actor = await task_client.get("/api/v1/actors/me", headers=auth_headers())
        assert actor.status_code == 200, actor.text
        path = f"/api/v1/projects/{project['id']}" if management else "/api/v1"
        before, previous = await snapshot(factory, task["id"])
        stored = before[0][0]
        assert stored["base_amount"] == Decimal("125.00") and stored["source_ref"] == "PRIVATE"
        assert stored["assigned_to"] == grant["actor_profile_id"] and stored["status"] == "claimed"
        response = await task_client.get(f"{path}/tasks/{task['id']}/work-context", headers=auth_headers())
        assert response.status_code == 200, response.text
        body = response.json()
        fields = COMMON | (MANAGEMENT if management else set())
        assert set(body) == CONTEXT | (set() if management else {"lifecycle"})
        assert set(body["task"]) == fields
        for name in fields - {"created_at", "updated_at", "deadline_at"}:
            assert body["task"][name] == stored["id" if name == "task_id" else name], name
        for name in ("created_at", "updated_at", "deadline_at"):
            assert datetime.fromisoformat(body["task"][name]) == stored[name]
        if not management:
            assert body["lifecycle"] == {"assigned_to_current_actor": True, "next_actions": ["start"]}
            assert "PRIVATE" not in response.text
        for kind in ("review", "revision"):
            assert body[f"{kind}_policy"] == {
                "policy_id": stored[f"locked_{kind}_policy_id"],
                "generation": stored[f"locked_{kind}_policy_generation"],
                "policy_hash": stored[f"locked_{kind}_policy_hash"],
            }
        assert body["contribution_policy_version_id"] == str(stored["locked_contribution_policy_version_id"])
        after, current = await snapshot(factory, task["id"])
        assert after == before and len(current - previous) == 1
        async with factory() as session:
            event = await session.get(AuditEvent, next(iter(current - previous)))
            assert (event.action_id, event.project_id, event.resource_id, event.actor_id) == (
                ACTIONS[int(management)], project["id"], project["id"], actor.json()["actor_profile_id"],
            )
            assert event.resource_type == "project"
            assert set(event.after_facts) == {"allowed", "resource_context_digest"}
            assert event.after_facts["allowed"] is True
            assert re.fullmatch(r"sha256:[0-9a-f]{64}", event.after_facts["resource_context_digest"])


async def test_work_context_owned_state_matrix(task_client, monkeypatch):
    project = await create_active_project(task_client)
    draft = await create_draft_task(task_client, project["id"])
    task = await create_started_task(task_client, project["id"], monkeypatch)
    denied = await task_client.get(f"/api/v1/tasks/{draft['id']}/work-context", headers=auth_headers())
    assert denied.status_code == 403 and denied.json()["error"]["code"] == "permission_not_granted"
    states = {state for edge in ALLOWED_TASK_TRANSITIONS for state in edge}
    assert states == {"draft", "screening", "ready", "claimed", "in_progress", "submitted", "evaluation_pending", "review_pending", "needs_revision"}
    factory, seen = db_session.get_session_factory(), set()
    for state in states:
        async with factory() as session, session.begin():
            row = await session.get(WorkstreamTask, task["id"])
            assert row.locked_contribution_policy_version_id is not None
            row.status = state  # Projection fixture only; preserves full locked custody and active assignment.
        async with factory() as session:
            row = await session.get(WorkstreamTask, task["id"])
            assignment = await session.scalar(select(TaskAssignment).where(TaskAssignment.task_id == row.id))
            assert row.status == state and assignment.status == "active"
            assert row.assigned_to == assignment.contributor_id
            assert row.locked_contribution_policy_version_id == assignment.submitter_contribution_policy_version_id
        response = await task_client.get(f"/api/v1/tasks/{task['id']}/work-context", headers=auth_headers())
        assert response.status_code == 200, (state, response.text)
        body = response.json()
        assert body["task"]["status"] == state
        assert body["lifecycle"] == {"assigned_to_current_actor": True, "next_actions": ["start"] if state == "claimed" else []}
        seen.add(body["task"]["status"])
    assert seen == states


@pytest.mark.parametrize("management", (False, True))
async def test_work_context_projection_failure_rolls_back(task_client, monkeypatch, management):
    project = await create_active_project(task_client)
    task = await create_started_task(task_client, project["id"], monkeypatch)
    if management:
        set_dev_actor(monkeypatch, roles="project_manager", subject="project-manager-subject")
    factory = db_session.get_session_factory()
    before, previous = await snapshot(factory, task["id"])
    actor = await task_client.get("/api/v1/actors/me", headers=auth_headers())
    assert actor.status_code == 200, actor.text
    captured = []

    async def unavailable(owner, request):
        assert request.task_id == UUID(task["id"]) and request.project_id == UUID(project["id"])
        detail = await original(owner, request)
        assert type(detail) is (ManagementTaskDetail if management else ContributorTaskDetail)
        assert detail.task_id == UUID(task["id"]) and detail.project_id == UUID(project["id"])
        staged = [event for event in await decisions(owner._session, task["id"]) if event.id not in previous]
        assert len(staged) == 1 and staged[0].after_facts["allowed"] is True
        assert staged[0].action_id == ACTIONS[int(management)] and staged[0].project_id == project["id"]
        assert staged[0].actor_id == actor.json()["actor_profile_id"]
        captured.append(staged[0].id)
        return None

    method = "read_management_task_detail" if management else "read_contributor_task_detail"
    original = getattr(TaskRepository, method)
    monkeypatch.setattr(TaskRepository, method, unavailable)
    path = f"/api/v1/projects/{project['id']}" if management else "/api/v1"
    response = await task_client.get(f"{path}/tasks/{task['id']}/work-context", headers=auth_headers())
    assert response.status_code == 404, response.text
    assert response.json()["error"]["code"] == "resource_not_found"
    assert response.json()["error"]["retryable"] is False
    assert len(captured) == 1
    after, current = await snapshot(factory, task["id"])
    assert after == before and current == previous
    async with factory() as session:
        assert await session.get(AuditEvent, captured[0]) is None


async def test_work_context_project_scope(task_client):
    project = await create_active_project(task_client)
    foreign = await create_active_project(task_client, slug="foreign-context")
    task = await create_ready_task(task_client, foreign["id"])
    factory = db_session.get_session_factory()
    before, _ = await snapshot(factory, task["id"])
    assert before[0][0]["project_id"] == foreign["id"]
    valid = await task_client.get(f"/api/v1/projects/{foreign['id']}/tasks/{task['id']}/work-context", headers=auth_headers())
    assert valid.status_code == 200, valid.text
    before, previous = await snapshot(factory, task["id"])
    denied = await task_client.get(f"/api/v1/projects/{project['id']}/tasks/{task['id']}/work-context", headers=auth_headers())
    assert denied.status_code == 404 and denied.json()["error"]["code"] == "resource_not_found"
    assert await snapshot(factory, task["id"]) == (before, previous)


async def test_work_context_missing_locked_context(task_client, monkeypatch):
    project = await create_active_project(task_client)
    task = await create_draft_task(task_client, project["id"])
    factory = db_session.get_session_factory()
    before, previous = await snapshot(factory, task["id"])
    loader = TaskService._load_locked_task_context
    staged_ids = []

    async def observe_authorized_custody(owner, row):
        staged = [event for event in await decisions(owner._session, row.id) if event.id not in previous]
        assert len(staged) == 1 and staged[0].after_facts["allowed"] is True
        assert staged[0].action_id == ACTIONS[1] and staged[0].project_id == project["id"]
        staged_ids.append(staged[0].id)
        return await loader(owner, row)

    monkeypatch.setattr(TaskService, "_load_locked_task_context", observe_authorized_custody)
    response = await task_client.get(f"/api/v1/projects/{project['id']}/tasks/{task['id']}/work-context", headers=auth_headers())
    assert len(staged_ids) == 1
    assert response.status_code == 422, response.text
    assert response.json()["error"]["code"] == "task_locked_context_invalid"
    assert "locked_guide_version" in response.json()["error"]["details"]["missing_fields"]
    assert await snapshot(factory, task["id"]) == (before, previous)


def test_work_context_obsolete_symbols_absent():
    for name in ("TaskProjectContext", "TaskWorkerTaskContext", "TaskGuideContext", "TaskReviewPolicyContext",
                 "TaskRevisionPolicyContext", "TaskWorkerLifecycleContext", "TaskWorkContextResponse"):
        assert not hasattr(schemas, name)
    assert not hasattr(TaskService, "_work_context_response")
    assert not hasattr(TaskService, "_worker_safe_task_response")
    assert not hasattr(AuthorizedTaskCommands, "work_context")
