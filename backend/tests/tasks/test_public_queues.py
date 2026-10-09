"""Public queue selection, query-bound continuations and selected-column privacy."""

from datetime import UTC, datetime
from uuid import UUID
from app.core.identifiers import new_record_id

import pytest
from sqlalchemy import event, select

from app.db import session as db_session
from app.adapters.contributions import locked_compensation_terms_port
from app.modules.actors.models import ActorIdentityLink
from app.modules.tasks.models import WorkstreamTask
from app.modules.tasks.repository import TaskRepository
from app.modules.tasks.api import TaskQueueRequest
from tests.authorization.task_queues.support import PATHS
from tests.project_create_fixtures import grant_fixture_admin_role
from tests.test_tasks import (
    task_database_env as task_database_env, task_client as task_client,
    create_active_project, create_draft_task, create_ready_task,
    admit_and_grant_project_submitter, auth_headers, set_dev_actor,
)

METHODS = {"ready": "read_ready_tasks", "management": "read_management_tasks", "operational": "read_operational_tasks"}
COLUMNS = {
    "ready": {"id", "project_id", "title", "task_type", "difficulty", "skill_tags", "estimated_time_minutes", "created_at", "locked_contribution_policy_version_id"},
    "management": {"id", "project_id", "title", "task_type", "difficulty", "skill_tags", "estimated_time_minutes", "status", "deadline_at", "created_at", "updated_at"},
    "operational": {"id", "project_id", "status", "created_at", "updated_at"},
}


def queue_repository(session, kind):
    return TaskRepository(
        session,
        compensation_terms=locked_compensation_terms_port(session) if kind == "ready" else None,
    )


async def queue_actor(client, monkeypatch, project, kind):
    if kind == "ready":
        return await admit_and_grant_project_submitter(client, monkeypatch, project, "queue-contributor")
    if kind == "operational":
        async with db_session.get_session_factory()() as session, session.begin():
            link = await session.scalar(select(ActorIdentityLink).where(
                ActorIdentityLink.issuer == "flow-test", ActorIdentityLink.subject == "project-manager-subject",
            ))
            await grant_fixture_admin_role(session, link.actor_profile_id, role="operator", scope="system")


@pytest.mark.parametrize("kind", PATHS)
async def test_public_queue_pages_preserve_owner_selection(task_client, monkeypatch, kind):
    project = await create_active_project(task_client)
    foreign = await create_active_project(task_client, slug="foreign-public-queue")
    outsider = await create_ready_task(task_client, foreign["id"])
    draft = await create_draft_task(task_client, project["id"])
    ready = [await create_ready_task(task_client, project["id"]) for _ in range(3)]
    async with db_session.get_session_factory()() as session, session.begin():
        for value in (outsider, draft, *ready):
            row = await session.get(WorkstreamTask, value["id"])
            row.created_at = datetime(2026, 1, 1, tzinfo=UTC)
    await admit_and_grant_project_submitter(task_client, monkeypatch, project["id"], "already-claimed")
    claimed = await task_client.post(f"/api/v1/tasks/{ready[-1]['id']}/claim", headers=auth_headers())
    assert claimed.status_code == 200, claimed.text
    set_dev_actor(monkeypatch, roles="", subject="project-manager-subject")
    await queue_actor(task_client, monkeypatch, project["id"], kind)
    path = PATHS[kind].format(project=project["id"])
    expected = sorted(item["id"] for item in (ready[:-1] if kind == "ready" else [draft, *ready]))
    seen, cursor = [], None
    for index in range(len(expected)):
        params = {"limit": 1} | ({"cursor": cursor} if cursor else {})
        response = await task_client.get(path, params=params, headers=auth_headers())
        assert response.status_code == 200, response.text
        page = response.json()
        assert page["project_id"] == project["id"]
        assert len(page["items"]) == 1
        item = page["items"][0]
        expected_fields = (COLUMNS[kind] - {"id", "locked_contribution_policy_version_id"}) | {"task_id"}
        if kind == "ready":
            expected_fields.add("compensation")
        assert set(item) == expected_fields
        assert item["project_id"] == project["id"]
        seen.append(item["task_id"])
        cursor = page["next_cursor"]
        assert (cursor is not None) == (index < len(expected) - 1)
    assert seen == expected


@pytest.mark.parametrize("kind", PATHS)
async def test_queue_selects_only_declared_columns(task_client, monkeypatch, kind):
    project = await create_active_project(task_client)
    await create_ready_task(task_client, project["id"])
    engine = db_session.get_session_factory().kw["bind"].sync_engine
    observed = []

    def capture(conn, clause, *args):
        if getattr(clause, "is_select", False) and any(
            getattr(column, "table", None) is WorkstreamTask.__table__ for column in clause.selected_columns
        ):
            observed.append(clause)

    event.listen(engine, "before_execute", capture)
    try:
        async with db_session.get_session_factory()() as session:
            page = await getattr(queue_repository(session, kind), METHODS[kind])(TaskQueueRequest(UUID(project["id"])))
            assert len(page.items) == 1
    finally:
        event.remove(engine, "before_execute", capture)
    assert len(observed) == 1
    assert {column.name for column in observed[0].selected_columns} == COLUMNS[kind]
    assert observed[0]._for_update_arg is None
    original = TaskRepository._read_task_queue_rows

    async def extra_column(repository, request, statement):
        return await original(repository, request, statement.add_columns(WorkstreamTask.description))

    monkeypatch.setattr(TaskRepository, "_read_task_queue_rows", extra_column)
    observed.clear()
    event.listen(engine, "before_execute", capture)
    try:
        async with db_session.get_session_factory()() as session:
            await getattr(queue_repository(session, kind), METHODS[kind])(TaskQueueRequest(UUID(project["id"])))
    finally:
        event.remove(engine, "before_execute", capture)
    assert len(observed) == 1
    with pytest.raises(AssertionError):
        assert {column.name for column in observed[0].selected_columns} == COLUMNS[kind]
    assert "description" in {column.name for column in observed[0].selected_columns}


async def test_cursor_binds_query_and_rechecks_authority(task_client, monkeypatch):
    project = await create_active_project(task_client)
    foreign = await create_active_project(task_client, slug="foreign-cursor")
    tasks = [await create_ready_task(task_client, project["id"]) for _ in range(3)]
    path = PATHS["management"].format(project=project["id"])
    first = await task_client.get(path, params={"limit": 1}, headers=auth_headers())
    assert first.status_code == 200, first.text
    cursor = first.json()["next_cursor"]
    assert cursor is not None
    # Each altered request has its own valid grant. Failure must be the cursor binding.
    await queue_actor(task_client, monkeypatch, project["id"], "operational")
    for altered_path, params in (
        (path, {"limit": 2, "cursor": cursor}),
        (PATHS["management"].format(project=foreign["id"]), {"limit": 1, "cursor": cursor}),
        (PATHS["operational"].format(project=project["id"]), {"limit": 1, "cursor": cursor}),
        (path, {"limit": 1, "cursor": cursor[:-1] + "!"}),
        (path, {"limit": 1, "cursor": "malformed"}),
    ):
        async def forbidden_read(*args, **kwargs):
            raise AssertionError("invalid cursor reached TASK projection")
        with monkeypatch.context() as guard:
            guard.setattr(TaskRepository, "_read_task_queue_rows", forbidden_read)
            response = await task_client.get(altered_path, params=params, headers=auth_headers())
        assert response.status_code == 422, response.text
    second = await task_client.get(path, params={"limit": 1, "cursor": cursor}, headers=auth_headers())
    assert second.status_code == 200, second.text
    assert second.json()["items"][0]["task_id"] == tasks[1]["id"]
    await queue_actor(task_client, monkeypatch, project["id"], "ready")
    ready_path = PATHS["ready"].format(project=project["id"])
    first = await task_client.get(ready_path, params={"limit": 1}, headers=auth_headers())
    cursor = first.json()["next_cursor"]
    claimed = await task_client.post(f"/api/v1/tasks/{tasks[1]['id']}/claim", headers=auth_headers())
    assert claimed.status_code == 200, claimed.text
    continued = await task_client.get(ready_path, params={"limit": 1, "cursor": cursor}, headers=auth_headers())
    assert continued.status_code == 200, continued.text
    assert [x["task_id"] for x in continued.json()["items"]] == [tasks[2]["id"]]


@pytest.mark.parametrize("kind", PATHS)
@pytest.mark.parametrize("params", [{"limit": 0}, {"limit": 101}, {"limit": "bad"}, {"cursor": "x" * 513}])
async def test_queue_rejects_invalid_request_shape(task_client, kind, params):
    response = await task_client.get(PATHS[kind].format(project=new_record_id()), params=params, headers=auth_headers())
    assert response.status_code == 422, response.text
