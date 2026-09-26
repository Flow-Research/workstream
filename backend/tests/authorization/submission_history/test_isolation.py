"""Retained history ignores current assignment and does not lock foreign tasks."""

import asyncio
from uuid import UUID

import pytest
from sqlalchemy import select, func

from app.db import session as db_session
from app.modules.tasks.models import TaskAssignment, WorkstreamTask
from tests.test_tasks import auth_headers, set_dev_actor, admit_and_grant_project_submitter
from .test_reads import history_case, history_paths


@pytest.mark.parametrize("state", ["submitted", "evaluation_pending", "review_pending", "needs_revision", "ready"])
async def test_historical_owner_after_reassignment(task_client, monkeypatch, state):
    case = await history_case(task_client, monkeypatch)
    replacement = await admit_and_grant_project_submitter(task_client, monkeypatch, case[0], "replacement-contributor")
    # Retained-data scenario, not a claim that live post-Submission release is supported.
    async with db_session.get_session_factory()() as session, session.begin():
        assignment = await session.scalar(select(TaskAssignment).where(TaskAssignment.task_id == case[1], TaskAssignment.status == "active"))
        assignment.status = "released"
        assignment.released_at = await session.scalar(select(func.clock_timestamp()))
        task = await session.get(WorkstreamTask, case[1])
        task.status = state
        task.assigned_to = None if state == "ready" else replacement["actor_profile_id"]
    for path in history_paths(*case).values():
        assert (await task_client.get(path, headers=auth_headers())).status_code == 404
    set_dev_actor(monkeypatch, roles="", subject="worker-one")
    for path in history_paths(*case).values():
        response = await task_client.get(path, headers=auth_headers())
        assert response.status_code == 200, response.text
    set_dev_actor(monkeypatch, roles="", subject="project-manager-subject")
    for path in history_paths(*case, manager=True).values():
        assert (await task_client.get(path, headers=auth_headers())).status_code == 200


async def test_wrong_project_does_not_wait(task_client, monkeypatch):
    case = await history_case(task_client, monkeypatch)
    set_dev_actor(monkeypatch, roles="", subject="project-manager-subject")
    factory = db_session.get_session_factory()
    async with factory() as holder, holder.begin():
        await holder.execute(select(WorkstreamTask.id).where(WorkstreamTask.id == case[1]).with_for_update())
        for path in history_paths(str(UUID(int=17)), *case[1:], manager=True).values():
            response = await asyncio.wait_for(task_client.get(path, headers=auth_headers()), timeout=3)
            assert response.status_code == 404, response.text


async def test_cursor_scope_and_continuation(task_client, monkeypatch):
    from tests.submission_fixtures import seed_retained_submission
    from tests.test_tasks import complete_submission_payload
    case = await history_case(task_client, monkeypatch)
    async with db_session.get_session_factory()() as session, session.begin():
        task = await session.get(WorkstreamTask, case[1])
        task.status = "needs_revision"
    successor = await seed_retained_submission(case[1], complete_submission_payload("sha256:successor"), predecessor_id=case[2])
    path = history_paths(*case)["task.submission.list"]
    first = await task_client.get(path, headers=auth_headers(), params={"limit": 1})
    assert first.status_code == 200, first.text
    assert [item["id"] for item in first.json()["items"]] == [case[2]]
    cursor = first.json()["next_cursor"]
    assert cursor
    second = await task_client.get(path, headers=auth_headers(), params={"limit": 1, "cursor": cursor})
    assert second.status_code == 200, second.text
    assert [item["id"] for item in second.json()["items"]] == [successor]
    assert second.json()["next_cursor"] is None
    for params in ({"limit": 0}, {"limit": 101}, {"cursor": "bad"}, {"limit": 2, "cursor": cursor}):
        assert (await task_client.get(path, headers=auth_headers(), params=params)).status_code == 422
    alternate = history_paths(*case)["submission.checker_run.list"]
    assert (await task_client.get(alternate, headers=auth_headers(), params={"limit": 1, "cursor": cursor})).status_code == 422


@pytest.mark.parametrize("damage", ["actor", "project", "action", "parent", "unknown", "duplicate", "position", "naive"])
async def test_invalid_cursor_never_enters_private_projection(task_client, monkeypatch, damage):
    import base64
    import json
    from app.modules.tasks.submission_history import SubmissionHistoryRepository
    from tests.test_tasks import actor_id
    case = await history_case(task_client, monkeypatch)
    value = {"action": "task.submission.list", "actor_id": await actor_id("worker-one"),
             "project_id": case[0], "parent_id": case[1], "limit": 25,
             "position_id": case[2], "version": 1}
    if damage in {"actor", "project", "parent"}:
        value[damage + "_id"] = str(UUID(int=19))
    elif damage == "action":
        value["action"] = "project.task.submission.list"
    elif damage == "unknown":
        value["unexpected"] = True
    elif damage == "position":
        value["created_at"] = "2026-01-01T00:00:00Z"
    elif damage == "naive":
        del value["version"]
        value["created_at"] = "2026-01-01T00:00:00"
    raw = json.dumps(value)
    if damage == "duplicate":
        raw = '{"limit":25,' + raw[1:]
    cursor = base64.urlsafe_b64encode(raw.encode()).decode()
    async def forbidden(*args, **kwargs):
        pytest.fail("malformed cursor reached private projection")
    monkeypatch.setattr(SubmissionHistoryRepository, "read", forbidden)
    response = await task_client.get(history_paths(*case)["task.submission.list"],
                                    headers=auth_headers(), params={"cursor": cursor})
    assert response.status_code == 422, response.text
