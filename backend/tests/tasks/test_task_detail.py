"""Real PostgreSQL scope, visibility, projection and transaction proof for task detail."""

import asyncio
from dataclasses import FrozenInstanceError, asdict, replace
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch
from uuid import UUID
from app.core.identifiers import new_record_id

import pytest
from sqlalchemy import select

from app.db import session as db_session
from app.main import create_app
from app.modules.tasks.api import (
    ContributorTaskDetail, ContributorTaskDetailRequest,
    ManagementTaskDetail, ManagementTaskDetailRequest,
)
from app.modules.tasks.lifecycle import ALLOWED_TASK_TRANSITIONS
from app.modules.tasks.models import TaskAssignment, WorkstreamTask
from app.modules.tasks.repository import TaskRepository
from tests.test_tasks import (
    task_database_env as task_database_env, task_client as task_client,
    create_active_project, create_draft_task, create_ready_task,
    admit_and_grant_project_submitter, auth_headers, seed_task_test_actor,
)

READS = ("read_contributor_task_detail", "read_management_task_detail")
STATES = {state for transition in ALLOWED_TASK_TRANSITIONS for state in transition}
COMMON = {
    "task_id", "project_id", "title", "description", "task_type", "difficulty", "skill_tags",
    "estimated_time_minutes", "status", "acceptance_criteria", "rejection_criteria",
    "deadline_at", "created_at", "updated_at",
}
MANAGEMENT = {"source_type", "source_ref", "source_payload_hash", "import_batch_id", "external_task_id", "created_by", "assigned_to"}


def request_for(method, project_id, task_id, contributor_id=None):
    if method == READS[0]:
        return ContributorTaskDetailRequest(UUID(project_id), UUID(task_id), contributor_id or new_record_id())
    return ManagementTaskDetailRequest(UUID(project_id), UUID(task_id))


async def read_once(session, method, request):
    with patch.object(session, "execute", wraps=session.execute) as execute:
        result = await getattr(TaskRepository(session), method)(request)
    execute.assert_awaited_once()
    return result


def test_task_detail_contracts():
    assert STATES == {"draft", "screening", "ready", "claimed", "in_progress", "submitted",
                      "evaluation_pending", "review_pending", "needs_revision"}
    now, project, task, contributor = datetime.now(UTC), new_record_id(), new_record_id(), new_record_id()
    for request in (ManagementTaskDetailRequest(project, task), ContributorTaskDetailRequest(project, task, contributor)):
        for field in asdict(request):
            with pytest.raises(ValueError, match="request is invalid"):
                replace(request, **{field: "bad"})
        with pytest.raises(FrozenInstanceError):
            request.task_id = new_record_id()
    values = dict(task_id=task, project_id=project, title="Title", description="Instructions", task_type=None,
                  difficulty=None, skill_tags=("tag",), estimated_time_minutes=None, status="ready",
                  acceptance_criteria=None, rejection_criteria=None, deadline_at=None, created_at=now, updated_at=now)
    for item in (ContributorTaskDetail(**values), ManagementTaskDetail(
        **values, source_type="manual", source_ref=None, source_payload_hash=None, import_batch_id=None,
        external_task_id=None, created_by="creator", assigned_to=None,
    )):
        assert set(asdict(item)) == COMMON | (MANAGEMENT if type(item) is ManagementTaskDetail else set())
        for field, value in asdict(item).items():
            with pytest.raises(ValueError, match="facts are invalid"):
                replace(item, **{field: []})
        for field in ("created_at", "updated_at", "deadline_at"):
            with pytest.raises(ValueError, match="facts are invalid"):
                replace(item, **{field: datetime.now()})
        with pytest.raises(ValueError, match="facts are invalid"):
            replace(item, estimated_time_minutes=True)
        with pytest.raises(ValueError, match="facts are invalid"):
            replace(item, skill_tags=([],))
        with pytest.raises(FrozenInstanceError):
            item.title = "changed"
        assert not hasattr(item, "_sa_instance_state")


@pytest.mark.parametrize("method", READS)
async def test_task_detail_rejects_invalid_request(method):
    session = MagicMock()
    other = request_for(READS[1] if method == READS[0] else READS[0], str(new_record_id()), str(new_record_id()))
    for value in ({}, other):
        with pytest.raises(ValueError, match="request is invalid"):
            await getattr(TaskRepository(session), method)(value)
    session.execute.assert_not_called()


@pytest.mark.parametrize("method", READS)
async def test_task_detail_scope(task_client, method):
    project = await create_active_project(task_client)
    foreign = await create_active_project(task_client, slug="foreign-detail")
    local = await create_ready_task(task_client, project["id"])
    outsider = await create_ready_task(task_client, foreign["id"])
    draft = await create_draft_task(task_client, project["id"])
    async with db_session.get_session_factory()() as session:
        assert (await session.get(WorkstreamTask, outsider["id"])).project_id == foreign["id"]
        assert (await session.get(WorkstreamTask, local["id"])).status == "ready"
        for task_id in (outsider["id"], str(new_record_id())):
            assert await read_once(session, method, request_for(method, project["id"], task_id)) is None
        assert await read_once(session, method, request_for(method, str(new_record_id()), local["id"])) is None
        visible = await read_once(session, method, request_for(method, project["id"], local["id"]))
        assert visible.task_id == UUID(local["id"]) and visible.project_id == UUID(project["id"])
        result = await read_once(session, method, request_for(method, project["id"], draft["id"]))
        if method == READS[0]:
            assert result is None
        else:
            assert result.status == "draft" and result.task_id == UUID(draft["id"])


async def test_task_detail_visibility(task_client, monkeypatch):
    project = await create_active_project(task_client)
    names = ("claimed", "wrong_contributor", "wrong_assignee", "active_only", "unrelated", "released", "released_ready", "assignee_only")
    tasks = {name: await create_ready_task(task_client, project["id"]) for name in names}
    other = await seed_task_test_actor("detail-other")
    grant = await admit_and_grant_project_submitter(task_client, monkeypatch, project["id"], "detail-owner")
    owner = grant["actor_profile_id"]
    claimed = await task_client.post(f"/api/v1/tasks/{tasks['claimed']['id']}/claim", headers=auth_headers())
    assert claimed.status_code == 200, claimed.text
    # status, task assignee, assignment contributor, assignment status.
    cases = {
        "wrong_contributor": ("claimed", owner, other, "active"),
        "wrong_assignee": ("claimed", other, owner, "active"),
        "active_only": ("ready", None, owner, "active"),
        "unrelated": ("claimed", owner, None, None),
        "released": ("claimed", owner, owner, "released"),
        "released_ready": ("ready", None, owner, "released"),
        "assignee_only": ("ready", owner, None, None),
    }
    factory = db_session.get_session_factory()
    async with factory() as session, session.begin():
        for name, (status, assignee, contributor, assignment_status) in cases.items():
            row = await session.get(WorkstreamTask, tasks[name]["id"])
            row.status, row.assigned_to = status, assignee
            if contributor:
                session.add(TaskAssignment(
                    id=str(new_record_id()), task_id=row.id, project_id=row.project_id, contributor_id=contributor,
                    assigned_by=owner, status=assignment_status,
                    submitter_contribution_policy_version_id=row.locked_contribution_policy_version_id,
                ))
    async with factory() as session:
        for name, expected in cases.items():
            row = await session.get(WorkstreamTask, tasks[name]["id"])
            assignment = await session.scalar(select(TaskAssignment).where(TaskAssignment.task_id == row.id))
            assert (row.status, row.assigned_to, assignment.contributor_id if assignment else None,
                    assignment.status if assignment else None) == expected
        own = await session.get(WorkstreamTask, tasks["claimed"]["id"])
        own_assignment = await session.scalar(select(TaskAssignment).where(TaskAssignment.task_id == own.id))
        assert own.assigned_to == own_assignment.contributor_id == owner and own_assignment.status == "active"
        for name in ("claimed", "unrelated", *(name for name in names if name not in {"claimed", "unrelated"})):
            result = await read_once(session, READS[0], request_for(READS[0], project["id"], tasks[name]["id"], UUID(owner)))
            if name in {"claimed", "released_ready"}:
                assert result.task_id == UUID(tasks[name]["id"])
            else:
                assert result is None, name
        assert await read_once(session, READS[0], request_for(READS[0], project["id"], own.id, UUID(other))) is None


async def test_task_detail_management_states(task_client):
    project = await create_active_project(task_client)
    states = STATES
    rows = {state: await create_ready_task(task_client, project["id"]) for state in states - {"draft"}}
    rows["draft"] = await create_draft_task(task_client, project["id"])
    factory = db_session.get_session_factory()
    async with factory() as session, session.begin():
        for state, value in rows.items():
            row = await session.get(WorkstreamTask, value["id"])
            if state != "draft":
                assert row.locked_contribution_policy_version_id is not None
                row.status = state  # Read fixture only, not execution of later lifecycle operations.
    async with factory() as session:
        stored = (await session.scalars(select(WorkstreamTask).where(WorkstreamTask.project_id == project["id"]))).all()
        assert {row.status for row in stored} == states and len(stored) == 9
        for row in stored:
            result = await read_once(session, READS[1], request_for(READS[1], project["id"], row.id))
            assert (result.task_id, result.status) == (UUID(row.id), row.status)


async def test_task_detail_owned_states(task_client, monkeypatch):
    project = await create_active_project(task_client)
    task = await create_ready_task(task_client, project["id"])
    grant = await admit_and_grant_project_submitter(task_client, monkeypatch, project["id"], "detail-states")
    claimed = await task_client.post(f"/api/v1/tasks/{task['id']}/claim", headers=auth_headers())
    assert claimed.status_code == 200, claimed.text
    factory, seen = db_session.get_session_factory(), set()
    for state in STATES:
        async with factory() as session, session.begin():
            row = await session.get(WorkstreamTask, task["id"])
            assert row.locked_contribution_policy_version_id is not None
            row.status = state  # Includes locked draft; ordinary unassigned draft is tested separately.
        async with factory() as session:
            row = await session.get(WorkstreamTask, task["id"])
            assignment = await session.scalar(select(TaskAssignment).where(TaskAssignment.task_id == row.id))
            assert row.status == state and assignment.status == "active"
            assert row.assigned_to == assignment.contributor_id == grant["actor_profile_id"]
            result = await read_once(session, READS[0], request_for(READS[0], project["id"], row.id, UUID(row.assigned_to)))
            assert result is not None and (result.task_id, result.status) == (UUID(row.id), state)
            seen.add(result.status)
    assert seen == STATES and len(seen) == 9


@pytest.mark.parametrize("method", READS)
async def test_task_detail_projection(task_client, method):
    project = await create_active_project(task_client)
    task = await create_ready_task(task_client, project["id"])
    deadline, factory = datetime(2030, 5, 6, tzinfo=UTC), db_session.get_session_factory()
    async with factory() as session, session.begin():
        row = await session.get(WorkstreamTask, task["id"])
        row.source_ref = row.source_payload_hash = row.import_batch_id = row.external_task_id = row.created_by = "PRIVATE"
        row.deadline_at = deadline
    async with factory() as session:
        row = await session.get(WorkstreamTask, task["id"])
        assert row.deadline_at == deadline and row.assigned_to is None
        expected = {name: getattr(row, name) for name in COMMON - {"task_id", "project_id", "skill_tags"}}
        expected |= dict(task_id=UUID(row.id), project_id=UUID(row.project_id), skill_tags=tuple(row.skill_tags))
        fields = COMMON | (MANAGEMENT if method == READS[1] else set())
        if method == READS[1]:
            expected |= {name: getattr(row, name) for name in MANAGEMENT}
        execute = session.execute

        async def checked_execute(statement, *args, **kwargs):
            result = await execute(statement, *args, **kwargs)  # Actual database query, not a canned result.
            assert set(statement.selected_columns.keys()) == fields
            return result

        with patch.object(session, "execute", wraps=checked_execute) as observed:
            detail = await getattr(TaskRepository(session), method)(request_for(method, project["id"], row.id))
        observed.assert_awaited_once()
        assert type(detail) is (ManagementTaskDetail if method == READS[1] else ContributorTaskDetail)
        assert asdict(detail) == expected
        assert set(asdict(detail)) == fields
        if method == READS[0]:
            assert "PRIVATE" not in str(asdict(detail))
        row.skill_tags.append("mutation")
        assert detail.skill_tags == expected["skill_tags"]


@pytest.mark.parametrize("method", READS)
async def test_task_detail_transaction(task_client, method):
    project = await create_active_project(task_client)
    task = await create_ready_task(task_client, project["id"])
    factory, request = db_session.get_session_factory(), request_for(method, project["id"], task["id"])
    async with factory() as session:
        pending = WorkstreamTask(id=str(new_record_id()), project_id=project["id"])
        session.add(pending)
        assert await read_once(session, method, request) is not None and pending in session.new
        await session.rollback()
    async with factory() as session:
        row = await session.get(WorkstreamTask, task["id"])
        original = row.title
        row.title = "uncommitted detail marker"
        await session.flush()
        detail = await read_once(session, method, request)
        assert detail.title == "uncommitted detail marker" and session.in_transaction()
        await session.rollback()
    async with factory() as observer:
        assert (await observer.get(WorkstreamTask, task["id"])).title == original
        assert await observer.get(WorkstreamTask, pending.id) is None


@pytest.mark.parametrize("method", READS)
async def test_task_detail_nonlocking(task_client, method):
    project = await create_active_project(task_client)
    task = await create_ready_task(task_client, project["id"])
    factory = db_session.get_session_factory()
    async with factory() as writer, writer.begin():
        await writer.scalar(select(WorkstreamTask).where(WorkstreamTask.id == task["id"]).with_for_update())
        async with factory() as reader:
            detail = await asyncio.wait_for(read_once(reader, method, request_for(method, project["id"], task["id"])), timeout=5)
            assert detail.task_id == UUID(task["id"])


def test_task_detail_ports_have_exact_public_audiences():
    schema = create_app().openapi()
    assert "/api/v1/projects/{project_id}/tasks/{task_id}" in schema["paths"]

    def reference_paths(value, reference, path=()):
        if isinstance(value, dict):
            if value.get("$ref") == reference:
                yield path
            for key, child in value.items():
                yield from reference_paths(child, reference, (*path, key))
        elif isinstance(value, list):
            for index, child in enumerate(value):
                yield from reference_paths(child, reference, (*path, index))

    for audience in ("Contributor", "Management"):
        reference = f"#/components/schemas/{audience}TaskDetail"
        route = "/api/v1/tasks/{task_id}" if audience == "Contributor" else "/api/v1/projects/{project_id}/tasks/{task_id}"
        assert set(reference_paths(schema, reference)) == {
            ("components", "schemas", f"{audience}TaskWorkContext", "properties", "task"),
            ("paths", route, "get", "responses", "200", "content", "application/json", "schema"),
        }
    assert schema["paths"]["/api/v1/tasks/{task_id}"]["get"]["responses"]["200"]["content"]["application/json"]["schema"]["$ref"].endswith("/ContributorTaskDetail")
