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
    assert first.json()["items"][0]["version"] == 1
    assert first.json()["items"][0]["supersedes_submission_id"] is None
    assert second.json()["items"][0]["version"] == 2
    assert second.json()["items"][0]["supersedes_submission_id"] == case[2]
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


async def test_same_task_history_separates_contributors(task_client, monkeypatch):
    """Retained prerequisites prove projection isolation, not live post-submit reclaim."""
    from app.core.identifiers import new_record_id
    from app.modules.tasks.models import Submission
    from app.modules.tasks.submission_composition import build_submission
    from tests.test_tasks import actor_id

    case = await history_case(task_client, monkeypatch)
    other = await admit_and_grant_project_submitter(
        task_client, monkeypatch, case[0], "second-history-contributor",
    )
    other_submission_id = str(new_record_id())
    async with db_session.get_session_factory()() as session, session.begin():
        task = await session.get(WorkstreamTask, case[1])
        original = await session.get(Submission, case[2])
        # Historical rows with all production constraints enabled. This does
        # not activate assignment release/reclaim after a Submission exists.
        assignment = TaskAssignment(
            id=str(new_record_id()), project_id=case[0], task_id=case[1],
            submitter_contribution_policy_version_id=original.contribution_policy_version_id,
            contributor_id=other["actor_profile_id"], assigned_by="retained-prerequisite",
            status="released", released_at=await session.scalar(select(func.clock_timestamp())),
        )
        session.add(assignment)
        await session.flush()
        second = build_submission(
            submission_id=other_submission_id, task=task,
            contributor_id=other["actor_profile_id"], version=2,
            summary="Second contributor retained work", worker_attestation="Retained evidence",
            supersedes_submission_id=None,
            contribution_policy_version_id=assignment.submitter_contribution_policy_version_id,
            task_assignment_id=assignment.id,
        )
        session.add(second)
        await session.flush()
        second.locked_at = await session.scalar(select(func.clock_timestamp()))
    path = history_paths(*case)["task.submission.list"]
    for subject, expected in (("worker-one", case[2]), ("second-history-contributor", other_submission_id)):
        set_dev_actor(monkeypatch, roles="", subject=subject)
        response = await task_client.get(path, headers=auth_headers(), params={"limit": 1})
        assert response.status_code == 200, response.text
        assert [item["id"] for item in response.json()["items"]] == [expected]
        assert response.json()["next_cursor"] is None
        who = await actor_id(subject)
        async with db_session.get_session_factory()() as session:
            assert await session.scalar(select(Submission.contributor_id).where(Submission.id == expected)) == who
    set_dev_actor(monkeypatch, roles="", subject="project-manager-subject")
    response = await task_client.get(history_paths(*case, manager=True)["task.submission.list"], headers=auth_headers())
    assert response.status_code == 200, response.text
    assert [item["id"] for item in response.json()["items"]] == [case[2], other_submission_id]


@pytest.mark.parametrize("manager", [False, True])
async def test_checker_pagination_and_cursor_audit(task_client, monkeypatch, manager):
    """Retained runs exercise timestamp/id continuation and exact query evidence."""
    from datetime import timedelta
    from app.core.identifiers import new_record_id
    from app.core.hashing import canonical_json_hash
    from app.modules.checkers.models import CheckerRun
    from app.modules.tasks.models import AuditEvent, Submission
    from tests.test_tasks import actor_id

    case = await history_case(task_client, monkeypatch)
    async with db_session.get_session_factory()() as session, session.begin():
        original = await session.get(CheckerRun, case[3])
        template = {column.name: getattr(original, column.name) for column in CheckerRun.__table__.columns}
        original.is_current_for_submission = False
        await session.flush()
        earlier_id, tied_id = str(new_record_id()), str(new_record_id())
        for run_id, attempt, when, predecessor, current in (
            (earlier_id, 2, original.created_at - timedelta(hours=1), original.id, False),
            (tied_id, 3, original.created_at, earlier_id, True),
        ):
            values = dict(template)
            values.update(id=run_id, attempt_number=attempt, supersedes_checker_run_id=predecessor,
                          is_current_for_submission=current, created_at=when, queued_at=when,
                          started_at=when, completed_at=when)
            session.add(CheckerRun(**values))
            await session.flush()
        contributor_id = (await session.get(Submission, case[2])).contributor_id
    subject = "project-manager-subject" if manager else "worker-one"
    set_dev_actor(monkeypatch, roles="", subject=subject)
    who = await actor_id(subject)
    action = ("project." if manager else "") + "submission.checker_run.list"
    path = history_paths(*case, manager=manager)["submission.checker_run.list"]
    cursor = None
    for index, expected in enumerate((earlier_id, case[3], tied_id)):
        async with db_session.get_session_factory()() as session:
            previous_events = set(await session.scalars(select(AuditEvent.id).where(
                AuditEvent.actor_id == who, AuditEvent.action_id == action,
            )))
        params = {"limit": 1}
        if cursor is not None:
            params["cursor"] = cursor
        response = await task_client.get(path, headers=auth_headers(), params=params)
        assert response.status_code == 200, response.text
        assert [item["id"] for item in response.json()["items"]] == [expected]
        item = response.json()["items"][0]
        async with db_session.get_session_factory()() as session:
            stored = await session.get(CheckerRun, expected)
            assert item["submission_version"] == stored.submission_version
            assert item["attempt_number"] == stored.attempt_number
            assert item["supersedes_checker_run_id"] == stored.supersedes_checker_run_id
            if manager:
                for field in item:
                    if field.startswith("locked_"):
                        assert item[field] == getattr(stored, field)
        async with db_session.get_session_factory()() as session:
            events = list(await session.scalars(select(AuditEvent).where(
                AuditEvent.actor_id == who, AuditEvent.action_id == action,
                AuditEvent.id.not_in(previous_events),
            )))
            assert len(events) == 1
            assert events[0].after_facts["resource_context_digest"] == canonical_json_hash({"resource_context": {
                "resource_type": "submission_history", "resource_id": case[2],
                "scope_project_id": case[0], "task_id": case[1], "submission_id": case[2],
                "contributor_id": contributor_id, "actor_profile_id": who,
                "request_digest": canonical_json_hash({"action": action, "limit": 1, "cursor": cursor}),
            }})
        cursor = response.json()["next_cursor"]
        assert (cursor is None) is (index == 2)


@pytest.mark.parametrize("manager", [False, True])
async def test_checker_detail_resolves_parent_before_checker_lookup(task_client, monkeypatch, manager):
    from app.modules.checkers.history import CheckerHistoryRepository
    from tests.test_tasks import admit_and_grant_project_submitter
    case = await history_case(task_client, monkeypatch)
    if manager:
        set_dev_actor(monkeypatch, roles="", subject="project-manager-subject")
        project = str(UUID(int=123))
    else:
        await admit_and_grant_project_submitter(task_client, monkeypatch, case[0], "foreign-history-owner")
        project = case[0]
    async def forbidden(*args, **kwargs):
        pytest.fail("CHECKERS entered before immutable parent ownership resolved")
    monkeypatch.setattr(CheckerHistoryRepository, "read", forbidden)
    path = history_paths(project, *case[1:], manager=manager)["checker_run.read"]
    response = await task_client.get(path, headers=auth_headers())
    assert response.status_code == 404, response.text


@pytest.mark.parametrize("manager", [False, True])
async def test_checker_detail_rejects_foreign_run_under_owned_parent(task_client, monkeypatch, manager):
    from .test_storage import retained_pair
    from app.modules.checkers.history import CheckerHistoryRepository
    from app.modules.tasks.models import AuditEvent
    case, other = await retained_pair(task_client, monkeypatch)
    set_dev_actor(monkeypatch, roles="", subject="project-manager-subject" if manager else "worker-one")
    called = []
    original = CheckerHistoryRepository.read
    async def capture(self, **kwargs):
        called.append(kwargs)
        return await original(self, **kwargs)
    monkeypatch.setattr(CheckerHistoryRepository, "read", capture)
    path = history_paths(*case[:3], other[2], manager=manager)["checker_run.read"]
    response = await task_client.get(path, headers=auth_headers())
    assert response.status_code == 404, response.text
    assert len(called) == 1 and str(called[0]["submission_id"]) == case[2]
    async with db_session.get_session_factory()() as session:
        action = ("project." if manager else "") + "checker_run.read"
        assert await session.scalar(select(AuditEvent.id).where(AuditEvent.action_id == action)) is None
