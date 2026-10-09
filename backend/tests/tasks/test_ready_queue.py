"""Hidden ready queue isolation, live pagination, and caller transaction proof."""

import asyncio
from dataclasses import FrozenInstanceError, asdict, replace
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock
from uuid import UUID
from app.core.identifiers import new_record_id

import pytest
from sqlalchemy import select

from app.db import session as db_session
from app.adapters.contributions import locked_compensation_terms_port
from app.modules.tasks.api import (
    TaskCompensationTerms, TaskQueueCursor, ReadyTaskPage, TaskQueueRequest, ReadyTaskSummary,
)
from app.modules.tasks.models import TaskAssignment, WorkstreamTask
from app.modules.tasks.repository import TaskRepository
from tests.test_tasks import (
    task_database_env as task_database_env,
    task_client as task_client,
    create_active_project, create_draft_task, create_ready_task,
    admit_and_grant_project_submitter, auth_headers,
)


def task_reads(session):
    return TaskRepository(session, compensation_terms=locked_compensation_terms_port(session))


@pytest.mark.parametrize("value", [0, 101, True, False, 1.5, "5", None])
def test_ready_queue_request_validation(value):
    with pytest.raises(ValueError, match="request is invalid"):
        TaskQueueRequest(new_record_id(), limit=value)


def test_ready_queue_cursor_validation():
    project = new_record_id()
    instant = datetime.now(UTC)
    valid = TaskQueueCursor(project, instant, new_record_id())
    assert TaskQueueRequest(project, after=valid).after == valid
    for change in ({"project_id": "bad"}, {"task_id": "bad"}, {"created_at": instant.replace(tzinfo=None)}):
        with pytest.raises(ValueError, match="cursor is invalid"):
            replace(valid, **change)
    for cursor in (replace(valid, project_id=new_record_id()), {}, "cursor"):
        with pytest.raises(ValueError, match="cursor differs"):
            TaskQueueRequest(project, after=cursor)
    with pytest.raises(ValueError, match="request is invalid"):
        TaskQueueRequest(str(project))


async def test_ready_queue_rejects_non_request_before_database():
    session = MagicMock()
    with pytest.raises(ValueError, match="request is invalid"):
        await TaskRepository(session).read_ready_tasks({"project_id": str(new_record_id())})
    session.execute.assert_not_called()


def _assignment(task, *, status="active"):
    return TaskAssignment(
        id=str(new_record_id()), task_id=task.id, project_id=task.project_id,
        contributor_id=task.created_by, assigned_by=task.created_by, status=status,
        submitter_contribution_policy_version_id=task.locked_contribution_policy_version_id,
    )


async def test_ready_queue_filters_before_pagination(task_client):
    project = await create_active_project(task_client)
    foreign = await create_active_project(task_client, slug="foreign-queue")
    foreign_task = await create_ready_task(task_client, foreign["id"])
    draft = await create_draft_task(task_client, project["id"])
    active, first, second, assigned = [
        await create_ready_task(task_client, project["id"]) for _ in range(4)
    ]
    factory = db_session.get_session_factory()
    instant = datetime(2026, 1, 1, tzinfo=UTC)
    async with factory() as session, session.begin():
        for position, value in enumerate((draft, foreign_task, active, first, second, assigned)):
            task = await session.get(WorkstreamTask, value["id"])
            task.created_at = instant + timedelta(seconds=min(position, 3) if position < 5 else 4)
            if value == active:
                session.add(_assignment(task))
            if value == assigned:
                task.assigned_to = task.created_by
    # Assert each independent persisted counterexample before invoking the read.
    async with factory() as session:
        active_row = await session.get(WorkstreamTask, active["id"])
        assigned_row = await session.get(WorkstreamTask, assigned["id"])
        assert active_row.status == assigned_row.status == "ready"
        assert active_row.assigned_to is None and assigned_row.assigned_to is not None
        assignments = (await session.scalars(select(TaskAssignment))).all()
        assert [(row.task_id, row.status) for row in assignments] == [(active["id"], "active")]
        assert (await session.get(WorkstreamTask, draft["id"])).status == "draft"
        foreign_row = await session.get(WorkstreamTask, foreign_task["id"])
        assert foreign_row.project_id == foreign["id"] and foreign_row.status == "ready"
        assert foreign_row.assigned_to is None
        request = TaskQueueRequest(UUID(project["id"]), limit=1)
        expected = sorted((UUID(first["id"]), UUID(second["id"])))
        owner = task_reads(session)
        page = await owner.read_ready_tasks(request)
        assert [item.task_id for item in page.items] == expected[:1]
        assert page.next_cursor == TaskQueueCursor(request.project_id, instant + timedelta(seconds=3), expected[0])
        next_page = await owner.read_ready_tasks(replace(request, after=page.next_cursor))
        assert [item.task_id for item in next_page.items] == expected[1:]
        assert next_page.next_cursor is None
        empty = await owner.read_ready_tasks(replace(
            request, after=TaskQueueCursor(request.project_id, instant + timedelta(seconds=3), expected[1]),
        ))
        assert empty == ReadyTaskPage(request.project_id, (), None)
        missing = await owner.read_ready_tasks(TaskQueueRequest(new_record_id()))
        assert missing.items == () and missing.next_cursor is None
    # An absent position past the final row must not restart pagination.
    missing_cursor = TaskQueueCursor(request.project_id, instant + timedelta(seconds=4), new_record_id())
    async with factory() as session:
        assert await session.get(WorkstreamTask, str(missing_cursor.task_id)) is None
        continued = await task_reads(session).read_ready_tasks(replace(request, after=missing_cursor))
        assert continued.items == () and continued.next_cursor is None



async def test_ready_queue_continues_after_claim(task_client, monkeypatch):
    project = await create_active_project(task_client)
    first = await create_ready_task(task_client, project["id"])
    second = await create_ready_task(task_client, project["id"])
    factory = db_session.get_session_factory()
    request = TaskQueueRequest(UUID(project["id"]), limit=1)
    async with factory() as session:
        page = await task_reads(session).read_ready_tasks(request)
        assert [item.task_id for item in page.items] == [UUID(first["id"])]
        assert page.next_cursor is not None
    await admit_and_grant_project_submitter(task_client, monkeypatch, project["id"], "queue-contributor")
    claimed = await task_client.post(
        f"/api/v1/tasks/{first['id']}/claim", headers=auth_headers(), json={"reason": "queue choice"},
    )
    assert claimed.status_code == 200, claimed.text
    async with factory() as session:
        assert (await session.get(WorkstreamTask, first["id"])).status == "claimed"
        owner = task_reads(session)
        for query in (request, replace(request, after=page.next_cursor)):
            current = await owner.read_ready_tasks(query)
            assert [item.task_id for item in current.items] == [UUID(second["id"])]
            assert current.next_cursor is None


async def test_ready_queue_assignment_visibility(task_client):
    project = await create_active_project(task_client)
    task = await create_ready_task(task_client, project["id"])
    factory = db_session.get_session_factory()
    async with factory() as session, session.begin():
        row = await session.get(WorkstreamTask, task["id"])
        assignment = _assignment(row, status="released")
        session.add(assignment)
    async with factory() as session:
        page = await task_reads(session).read_ready_tasks(TaskQueueRequest(UUID(project["id"])))
        assert [item.task_id for item in page.items] == [UUID(task["id"])]
        assert page.next_cursor is None


async def test_ready_queue_detached_projection(task_client):
    project = await create_active_project(task_client)
    task = await create_ready_task(task_client, project["id"])
    async with db_session.get_session_factory()() as session:
        row = await session.get(WorkstreamTask, task["id"])
        page = await task_reads(session).read_ready_tasks(TaskQueueRequest(UUID(project["id"])))
        expected = ReadyTaskSummary(
            UUID(row.id), UUID(row.project_id), row.title, row.task_type, row.difficulty,
            tuple(row.skill_tags), row.estimated_time_minutes, row.created_at,
            TaskCompensationTerms(row.locked_contribution_policy_version_id, "unpaid", "unpaid"),
        )
        assert page.items == (expected,) and page.next_cursor is None
        assert set(asdict(page.items[0])) == {
            "task_id", "project_id", "title", "task_type", "difficulty", "skill_tags",
            "estimated_time_minutes", "created_at", "compensation",
        }
        row.skill_tags.append("private mutation")
        assert page.items[0].skill_tags == ("stem", "proofs")
        with pytest.raises(FrozenInstanceError):
            page.items[0].title = "changed"
        assert not hasattr(page.items[0], "_sa_instance_state")
        for changed in ({"skill_tags": []}, {"task_id": "bad"}, {"title": []},
                        {"task_type": []}, {"difficulty": []}, {"estimated_time_minutes": True},
                        {"created_at": datetime.now()}, {"skill_tags": ([],)}):
            with pytest.raises(ValueError, match="summary is invalid"):
                replace(expected, **changed)
        with pytest.raises(ValueError, match="page is invalid"):
            replace(page, project_id=new_record_id())
        with pytest.raises(ValueError, match="continuation differs"):
            replace(page, next_cursor=TaskQueueCursor(page.project_id, expected.created_at, new_record_id()))


async def test_ready_queue_preserves_transaction(task_client):
    project = await create_active_project(task_client)
    task = await create_ready_task(task_client, project["id"])
    factory = db_session.get_session_factory()
    request = TaskQueueRequest(UUID(project["id"]))
    async with factory() as session:
        assert not session.in_transaction()
        assert len((await task_reads(session).read_ready_tasks(request)).items) == 1
        pending = WorkstreamTask(id=str(new_record_id()), project_id=project["id"])
        session.add(pending)  # Missing required fields: any implicit flush fails.
        assert len((await task_reads(session).read_ready_tasks(request)).items) == 1
        assert pending in session.new
        await session.rollback()
    # Separate control: prove no commit without an invalid pending row masking it.
    async with factory() as session:
        row = await session.get(WorkstreamTask, task["id"])
        row.title = "Uncommitted marker"
        await session.flush()
        page = await task_reads(session).read_ready_tasks(request)
        assert page.items[0].title == "Uncommitted marker" and session.in_transaction()
        await session.rollback()
    async with factory() as observer:
        assert (await observer.get(WorkstreamTask, task["id"])).title == task["title"]
        assert await observer.get(WorkstreamTask, pending.id) is None


async def test_ready_queue_does_not_wait_for_task_lock(task_client):
    project = await create_active_project(task_client)
    task = await create_ready_task(task_client, project["id"])
    factory = db_session.get_session_factory()
    async with factory() as writer, writer.begin():
        await writer.scalar(select(WorkstreamTask).where(WorkstreamTask.id == task["id"]).with_for_update())
        async with factory() as reader:
            page = await asyncio.wait_for(
                task_reads(reader).read_ready_tasks(TaskQueueRequest(UUID(project["id"]))),
                timeout=5,
            )
            assert [item.task_id for item in page.items] == [UUID(task["id"])]


async def test_public_queue_openapi_contract(task_client):
    from tests.authorization.task_queues.support import PATHS, ACTIONS

    response = await task_client.get("/openapi.json")
    assert response.status_code == 200
    paths = response.json()["paths"]
    for kind, template in PATHS.items():
        route = paths[template.replace("{project}", "{project_id}")]["get"]
        assert route["x-workstream-action-id"] == ACTIONS[kind]
        assert route["responses"]["200"]["content"]["application/json"]["schema"]["$ref"].endswith({
            "ready": "ContributorTaskQueueResponse", "management": "ManagementTaskQueueResponse",
            "operational": "OperationalTaskQueueResponse",
        }[kind])
    assert paths["/api/v1/projects/{project_id}/tasks"]["post"]["x-workstream-action-id"] == "project.task.create"
