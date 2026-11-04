"""Real PostgreSQL proof for hidden management and operational queue facts."""

import asyncio
from dataclasses import FrozenInstanceError, asdict, replace
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch
from uuid import UUID
from app.core.identifiers import new_record_id

import pytest
from sqlalchemy import select

from app.db import session as db_session
from app.modules.tasks.api import (
    ManagementTaskPage, ManagementTaskSummary, OperationalTaskPage,
    OperationalTaskSummary, TaskQueueCursor, TaskQueueRequest,
)
from app.modules.tasks.lifecycle import ALLOWED_TASK_TRANSITIONS
from app.modules.tasks.models import TaskAssignment, WorkstreamTask
from app.modules.tasks.repository import TaskRepository
from tests.test_tasks import (
    task_database_env as task_database_env, task_client as task_client,
    create_active_project, create_draft_task, create_ready_task,
    admit_and_grant_project_submitter, auth_headers,
)

READS = ("read_management_tasks", "read_operational_tasks")


@pytest.mark.parametrize("method", READS)
async def test_management_queue_rejects_non_request(method):
    session = MagicMock()
    with pytest.raises(ValueError, match="request is invalid"):
        await getattr(TaskRepository(session), method)({"project_id": str(new_record_id())})
    session.execute.assert_not_called()


def test_management_queue_contract_validation():
    now, project, task = datetime.now(UTC), new_record_id(), new_record_id()
    management = ManagementTaskSummary(task, project, "Task", None, None, (), None, "draft", None, now, now)
    operational = OperationalTaskSummary(task, project, "draft", now, now)
    for item in (management, operational):
        for change in ({"task_id": "bad"}, {"project_id": "bad"}, {"status": []},
                       {"created_at": datetime.now()}, {"updated_at": datetime.now()}):
            with pytest.raises(ValueError, match="summary is invalid"):
                replace(item, **change)
        with pytest.raises(FrozenInstanceError):
            item.status = "ready"
    for change in ({"title": []}, {"task_type": []}, {"difficulty": []}, {"skill_tags": []},
                   {"skill_tags": ([],)}, {"estimated_time_minutes": True}, {"deadline_at": datetime.now()}):
        with pytest.raises(ValueError, match="summary is invalid"):
            replace(management, **change)
    assert replace(management, deadline_at=now, estimated_time_minutes=5).deadline_at == now
    for page_type, item, wrong_item in (
        (ManagementTaskPage, management, operational), (OperationalTaskPage, operational, management),
    ):
        cursor = TaskQueueCursor(project, now, task)
        page = page_type(project, (item,), cursor)
        assert page.next_cursor == cursor
        for change in ({"project_id": "bad"}, {"project_id": new_record_id()}, {"items": []},
                       {"items": (wrong_item,)}, {"items": (item,) * 101}):
            with pytest.raises(ValueError, match="page is invalid"):
                replace(page, **change)
        for change in ({"items": ()}, {"next_cursor": {}},
                       {"next_cursor": replace(cursor, task_id=new_record_id())}):
            with pytest.raises(ValueError, match="continuation differs"):
                replace(page, **change)


@pytest.mark.parametrize("method", READS)
async def test_management_queue_pagination(task_client, monkeypatch, method):
    project = await create_active_project(task_client)
    foreign = await create_active_project(task_client, slug="foreign-management")
    outsiders = [await create_draft_task(task_client, foreign["id"]) for _ in range(2)]
    draft = await create_draft_task(task_client, project["id"])
    ready, claimed = [await create_ready_task(task_client, project["id"]) for _ in range(2)]
    await admit_and_grant_project_submitter(task_client, monkeypatch, project["id"], "queue-manager-fixture")
    response = await task_client.post(f"/api/v1/tasks/{claimed['id']}/claim", headers=auth_headers())
    assert response.status_code == 200, response.text
    factory = db_session.get_session_factory()
    now = datetime(2026, 1, 1, tzinfo=UTC)
    async with factory() as session, session.begin():
        for value, offset in ((outsiders[0], -1), (draft, 0), (outsiders[1], 1), (ready, 2), (claimed, 2)):
            row = await session.get(WorkstreamTask, value["id"])
            row.created_at = now + timedelta(seconds=offset)
    async with factory() as session:
        local = (await session.scalars(select(WorkstreamTask).where(WorkstreamTask.project_id == project["id"]))).all()
        assert {row.status for row in local} == {"draft", "ready", "in_progress"}
        assignment = await session.scalar(select(TaskAssignment).where(TaskAssignment.task_id == claimed["id"]))
        assert assignment.status == "active" and assignment.contributor_id is not None
        assert (await session.get(WorkstreamTask, claimed["id"])).assigned_to == assignment.contributor_id
        assert {row.project_id for row in (await session.scalars(select(WorkstreamTask))).all()} == {
            project["id"], foreign["id"],
        }
        read = getattr(TaskRepository(session), method)
        request = TaskQueueRequest(UUID(project["id"]), limit=1)
        expected = [UUID(draft["id"]), *sorted((UUID(ready["id"]), UUID(claimed["id"])))]
        seen, first_cursor = [], None
        for index, task_id in enumerate(expected):
            page = await read(request)
            assert [item.task_id for item in page.items] == [task_id]
            seen.append(page.items[0].task_id)
            if index < len(expected) - 1:
                assert page.next_cursor == TaskQueueCursor(request.project_id, page.items[0].created_at, task_id)
                first_cursor = first_cursor or page.next_cursor
                request = replace(request, after=page.next_cursor)
            else:
                assert page.next_cursor is None
        assert seen == expected
        end = await read(replace(request, after=TaskQueueCursor(request.project_id, now + timedelta(seconds=2), expected[-1])))
        assert end.items == () and end.next_cursor is None
        missing = await read(TaskQueueRequest(new_record_id()))
        assert missing.items == () and missing.next_cursor is None
    # A cursor is a position, not a foreign key to a retained task.
    missing_cursor = replace(first_cursor, task_id=new_record_id(), created_at=first_cursor.created_at + timedelta(microseconds=1))
    async with factory() as session:
        assert await session.get(WorkstreamTask, str(missing_cursor.task_id)) is None
        continued = await getattr(TaskRepository(session), method)(replace(request, after=missing_cursor))
        assert [item.task_id for item in continued.items] == expected[1:2]
        foreign_page = await getattr(TaskRepository(session), method)(TaskQueueRequest(UUID(foreign["id"])))
        assert {item.task_id for item in foreign_page.items} == {UUID(row["id"]) for row in outsiders}



@pytest.mark.parametrize("method", READS)
async def test_management_queue_all_states(task_client, monkeypatch, method):
    """Later statuses are read fixtures, not claims that later lifecycle commands ran."""
    states = {"draft", "screening", "ready", "in_progress", "submitted",
              "evaluation_pending", "review_pending", "needs_revision"}
    assert states == {state for transition in ALLOWED_TASK_TRANSITIONS for state in transition}
    project = await create_active_project(task_client)
    rows = {"draft": await create_draft_task(task_client, project["id"])}
    for status in sorted(states - {"draft"}):
        rows[status] = await create_ready_task(task_client, project["id"])
    await admit_and_grant_project_submitter(task_client, monkeypatch, project["id"], "all-states-contributor")
    response = await task_client.post(f"/api/v1/tasks/{rows['in_progress']['id']}/claim", headers=auth_headers())
    assert response.status_code == 200, response.text
    factory = db_session.get_session_factory()
    async with factory() as session, session.begin():
        for status in states - {"draft", "ready", "in_progress"}:
            row = await session.get(WorkstreamTask, rows[status]["id"])
            assert row.locked_contribution_policy_version_id is not None
            row.status = status  # Fully locked fixture; no database guards disabled.
    async with factory() as session:
        stored = (await session.scalars(select(WorkstreamTask).where(WorkstreamTask.project_id == project["id"]))).all()
        expected = {UUID(row.id): row.status for row in stored}
        assert set(expected.values()) == states and len(expected) == 8
        page = await getattr(TaskRepository(session), method)(TaskQueueRequest(UUID(project["id"])))
        assert {item.task_id: item.status for item in page.items} == expected
        assert page.next_cursor is None


async def test_management_queue_projection(task_client):
    project = await create_active_project(task_client)
    task = await create_draft_task(task_client, project["id"])
    deadline = datetime(2030, 5, 6, 7, 8, tzinfo=UTC)
    factory = db_session.get_session_factory()
    async with factory() as session, session.begin():
        row = await session.get(WorkstreamTask, task["id"])
        row.title = row.description = row.source_ref = row.acceptance_criteria = "PRIVATE-CONTENT"
        row.skill_tags = ["PRIVATE-TAG"]
        row.deadline_at = deadline
    async with factory() as session:
        row = await session.get(WorkstreamTask, task["id"])
        assert row.deadline_at == deadline
        owner, request = TaskRepository(session), TaskQueueRequest(UUID(project["id"]))
        management = (await owner.read_management_tasks(request)).items[0]
        with patch.object(session, "execute", wraps=session.execute) as execute:
            operational = (await owner.read_operational_tasks(request)).items[0]
        execute.assert_awaited_once()
        statement = execute.call_args.args[0]
        assert set(statement.selected_columns.keys()) == {"id", "project_id", "status", "created_at", "updated_at"}
        assert management == ManagementTaskSummary(
            UUID(row.id), UUID(row.project_id), row.title, row.task_type, row.difficulty, tuple(row.skill_tags),
            row.estimated_time_minutes, row.status, row.deadline_at, row.created_at, row.updated_at,
        )
        assert set(asdict(management)) == {"task_id", "project_id", "title", "task_type", "difficulty", "skill_tags",
                                            "estimated_time_minutes", "status", "deadline_at", "created_at", "updated_at"}
        assert operational == OperationalTaskSummary(UUID(row.id), UUID(row.project_id), row.status, row.created_at, row.updated_at)
        assert set(asdict(operational)) == {"task_id", "project_id", "status", "created_at", "updated_at"}
        assert "PRIVATE" not in str(asdict(operational))
        row.skill_tags.append("mutation")
        assert management.skill_tags == ("PRIVATE-TAG",)
        assert not hasattr(management, "_sa_instance_state") and not hasattr(operational, "_sa_instance_state")


@pytest.mark.parametrize("method", READS)
async def test_management_queue_transaction(task_client, method):
    project = await create_active_project(task_client)
    task = await create_ready_task(task_client, project["id"])
    factory, request = db_session.get_session_factory(), TaskQueueRequest(UUID(project["id"]))
    async with factory() as session:
        pending = WorkstreamTask(id=str(new_record_id()), project_id=project["id"])
        session.add(pending)
        assert len((await getattr(TaskRepository(session), method)(request)).items) == 1
        assert pending in session.new and session.in_transaction()
        await session.rollback()
    async with factory() as session:
        row = await session.get(WorkstreamTask, task["id"])
        row.status = "screening"
        await session.flush()
        page = await getattr(TaskRepository(session), method)(request)
        assert page.items[0].status == "screening" and session.in_transaction()
        await session.rollback()
    async with factory() as observer:
        assert (await observer.get(WorkstreamTask, task["id"])).status == "ready"
        assert await observer.get(WorkstreamTask, pending.id) is None


@pytest.mark.parametrize("method", READS)
async def test_management_queue_nonlocking(task_client, method):
    project = await create_active_project(task_client)
    task = await create_draft_task(task_client, project["id"])
    factory = db_session.get_session_factory()
    async with factory() as writer, writer.begin():
        await writer.scalar(select(WorkstreamTask).where(WorkstreamTask.id == task["id"]).with_for_update())
        async with factory() as reader:
            page = await asyncio.wait_for(getattr(TaskRepository(reader), method)(TaskQueueRequest(UUID(project["id"]))), 5)
            assert [item.task_id for item in page.items] == [UUID(task["id"])]
