"""Signed project keyset pages: stable order, no gaps or duplicates, exact updated_since and filters."""

from sqlalchemy import func, select, text

from app.db import session as db_session
from tests.contributor_reads.support import OTHER, start_another
from tests.submission_fixtures import seed_retained_submission
from tests.test_tasks import (
    actor_id, auth_headers, complete_submission_payload, create_started_task, set_dev_actor,
)
from .support import EXACT_MANAGER, OWNER, as_admin, as_manager, get_ok, project_path, submitted_case


async def _walk(client, path, **params):
    """Follow every continuation at page size one and return the ordered rows."""
    rows, cursor = [], None
    while True:
        page = await get_ok(client, path, limit=1, **params, **({"cursor": cursor} if cursor else {}))
        rows.extend(page["items"])
        cursor = page["next_cursor"]
        if cursor is None:
            return rows
        assert len(page["items"]) == 1


async def _clock():
    async with db_session.get_session_factory()() as session:
        return await session.scalar(select(func.clock_timestamp()))


async def _touch(table, ids):
    """A committed no-op update moves only the DB-maintained stamp."""
    async with db_session.get_session_factory()() as session, session.begin():
        await session.execute(text(f"UPDATE public.{table} SET status=status WHERE id = ANY(CAST(:ids AS uuid[]))"),
                              {"ids": ids})


async def _two_contributors(client, monkeypatch):
    """worker-one holds three submitted tasks and worker-two one, all in one project."""
    project, first, _submission = await submitted_case(client, monkeypatch)
    owner_tasks = [first]
    for index in range(2):
        task = await start_another(client, monkeypatch, project)
        await seed_retained_submission(task, complete_submission_payload(f"sha256:owner-{index}"))
        owner_tasks.append(task)
    other_task = (await create_started_task(client, project, monkeypatch, subject=OTHER))["id"]
    await seed_retained_submission(other_task, complete_submission_payload("sha256:other"))
    as_manager(monkeypatch)
    return project, owner_tasks, other_task


async def test_submission_pages_are_complete_ordered_and_exactly_incremental(task_client, monkeypatch):
    project, owner_tasks, other_task = await _two_contributors(task_client, monkeypatch)
    path = project_path(project, "/submissions")
    rows = await _walk(task_client, path)
    assert sorted(row["task_id"] for row in rows) == sorted([*owner_tasks, other_task])
    assert len({row["submission_id"] for row in rows}) == 4
    assert [(row["updated_at"], row["submission_id"]) for row in rows] == sorted(
        (row["updated_at"], row["submission_id"]) for row in rows)
    since = await _clock()
    changed = sorted([rows[0]["submission_id"], rows[3]["submission_id"]])
    await _touch("submissions", changed)
    later = await _walk(task_client, path, updated_since=since.isoformat())
    assert sorted(row["submission_id"] for row in later) == changed


async def test_submission_filters_select_exactly_their_rows(task_client, monkeypatch):
    project, owner_tasks, other_task = await _two_contributors(task_client, monkeypatch)
    path = project_path(project, "/submissions")
    owner, other = await actor_id(OWNER), await actor_id(OTHER)
    mine = await _walk(task_client, path, submitter_actor_id=owner)
    assert sorted(row["task_id"] for row in mine) == sorted(owner_tasks)
    assert {row["submitter_actor_id"] for row in mine} == {owner}
    [theirs] = await _walk(task_client, path, submitter_actor_id=other)
    assert (theirs["task_id"], theirs["submitter_actor_id"]) == (other_task, other)
    [one] = await _walk(task_client, path, task_id=owner_tasks[1])
    assert one["task_id"] == owner_tasks[1]
    assert len(await _walk(task_client, path, status="evaluation_pending")) == 4
    assert await _walk(task_client, path, status="accepted") == []


async def test_assignment_pages_are_complete_ordered_and_filtered_by_state(task_client, monkeypatch):
    project, owner_tasks, other_task = await _two_contributors(task_client, monkeypatch)
    path = project_path(project, "/assignments")
    rows = await _walk(task_client, path)
    assert sorted(row["task_id"] for row in rows) == sorted([*owner_tasks, other_task])
    assert len({row["assignment_id"] for row in rows}) == 4
    assert [(row["updated_at"], row["assignment_id"]) for row in rows] == sorted(
        (row["updated_at"], row["assignment_id"]) for row in rows)
    assert {row["contributor_actor_id"] for row in rows} == {await actor_id(OWNER), await actor_id(OTHER)}
    assert len(await _walk(task_client, path, state="active")) == 4
    assert await _walk(task_client, path, state="closed") == []


async def test_cursor_is_bound_to_its_caller_project_endpoint_and_filters(task_client, monkeypatch):
    project, _owner_tasks, _other_task = await _two_contributors(task_client, monkeypatch)
    path = project_path(project, "/submissions")
    cursor = (await get_ok(task_client, path, limit=1))["next_cursor"]
    assert cursor is not None

    async def refused(target, **params):
        response = await task_client.get(target, params={"limit": 1, "cursor": cursor} | params,
                                         headers=auth_headers())
        assert response.status_code == 422, (target, params, response.text)
        assert response.json()["error"]["code"] == "project_read_cursor_invalid"

    for params in ({"status": "evaluation_pending"}, {"task_id": _owner_tasks[0]}, {"limit": 2},
                   {"updated_since": "2026-01-01T00:00:00Z"}):
        await refused(path, **params)
    await refused(project_path(project, "/assignments"))
    await refused(project_path(project, "/task-import-batches"))
    # Another Project Manager of the same project cannot continue this page.
    await as_admin(task_client, monkeypatch, EXACT_MANAGER, "project_manager", project=project)
    await refused(path)
    set_dev_actor(monkeypatch, roles="", subject=EXACT_MANAGER)
    assert len(await _walk(task_client, path)) == 4
