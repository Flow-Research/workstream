"""Real originating authority mutations atomically append exact assignment work."""

from uuid import UUID

import pytest
from sqlalchemy import select

from app.core.identifiers import new_record_id
from app.modules.outbox.models import OutboxEvent
from app.modules.tasks.api.assignment_invalidation import ASSIGNMENT_INVALIDATION_EVENT
from tests.test_tasks import task_client as task_client, task_database_env as task_database_env
from tests.tasks.invalidation_support import setup_assignment, revoke


@pytest.mark.parametrize("kind", ["grant", "suspend", "deactivate", "link"])
async def test_supported_causes_publish_exact_targets(task_client, monkeypatch, kind):
    s = await setup_assignment(task_client, monkeypatch)
    await revoke(s, kind)
    async with s.sessions() as session:
        events = (await session.scalars(select(OutboxEvent))).all()
        assert len(events) == 1
        event = events[0]
        assert event.event_type == ASSIGNMENT_INVALIDATION_EVENT
        assert event.event_version == 1 and event.aggregate_type == "task_assignment"
        assert event.aggregate_id == UUID(s.assignment["id"])
        assert event.project_id == s.project["id"]
        assert event.causation_event_id == s.invalidation_id
        assert event.event_id.version == 7
        assert event.idempotency_key == (
            f"assignment-invalidation:{s.invalidation_id}:{s.assignment['id']}"
        )
        assert event.payload == {
            "project_id": s.project["id"], "task_id": s.task["id"],
            "assignment_id": s.assignment["id"], "contributor_id": s.grant["actor_profile_id"],
            "authority_invalidation_event_id": str(s.invalidation_id),
        }


@pytest.mark.parametrize("fail_after", [None, 100])
async def test_actor_fanout_publishes_every_page(task_client, monkeypatch, fail_after):
    """More than one query page either commits entirely or rolls back entirely."""
    from app.modules.actors.models import ActorProfile
    from app.modules.authorization.models import AuthorityIdempotencyRecord
    from app.modules.outbox.api import OutboxPersistenceError
    from app.modules.outbox.service import OutboxService
    from app.modules.tasks.models import AuditEvent
    from tests.test_tasks import auth_headers, set_dev_actor

    s = await setup_assignment(task_client, monkeypatch)
    expected = await _seed_additional_assignments(s, 100)
    async with s.sessions() as session:
        before_audit = set((await session.scalars(select(AuditEvent.id))).all())
        before_receipts = set((await session.scalars(select(AuthorityIdempotencyRecord.id))).all())
    calls = []
    original = OutboxService.append

    async def append(owner, value):
        calls.append(value.aggregate_id)
        if fail_after is not None and len(calls) > fail_after:
            raise OutboxPersistenceError("private database details")
        return await original(owner, value)

    monkeypatch.setattr(OutboxService, "append", append)
    set_dev_actor(monkeypatch, roles="viewer", issuer=s.admin_identity[0], subject=s.admin_identity[1])
    response = await task_client.post(
        f"/api/v1/actors/{s.grant['actor_profile_id']}/suspend",
        headers=auth_headers(), json={"reason": "Complete atomic fanout"},
    )
    assert response.status_code == (200 if fail_after is None else 503), response.text
    assert len(calls) == 101 and {str(value) for value in calls} == expected
    async with s.sessions() as session:
        events = (await session.scalars(select(OutboxEvent))).all()
        actor = await session.get(ActorProfile, s.grant["actor_profile_id"])
        if fail_after is None:
            assert response.status_code == 200, response.text
            assert {str(event.aggregate_id) for event in events} == expected
            assert actor.status == "suspended"
        else:
            assert response.status_code == 503, response.text
            assert "private database details" not in response.text
            assert events == [] and actor.status == "active"
            assert set((await session.scalars(select(AuditEvent.id))).all()) == before_audit
            assert set((await session.scalars(select(AuthorityIdempotencyRecord.id))).all()) == before_receipts


async def _seed_additional_assignments(s, count):
    """Scale a valid locked fixture without repeating unrelated HTTP setup.

    The original task/assignment came from real AUTH commands. Copies cross the
    database's draft -> screening stamp boundary, retaining all active guides,
    policies and real contributor grants; no trigger is disabled.
    """
    from sqlalchemy import insert, update
    from app.modules.tasks.models import WorkstreamTask, TaskAssignment

    expected = {s.assignment["id"]}
    async with s.sessions() as session, session.begin():
        original = dict((await session.execute(select(WorkstreamTask.__table__).where(
            WorkstreamTask.id == s.task["id"],
        ))).mappings().one())
        assignment = dict((await session.execute(select(TaskAssignment.__table__).where(
            TaskAssignment.id == s.assignment["id"],
        ))).mappings().one())
        locked = {key: value for key, value in original.items() if key.startswith("locked_")}
        for _ in range(count):
            task_id, assignment_id = str(new_record_id()), str(new_record_id())
            draft = original | {"id": task_id, "status": "draft", "assigned_to": None}
            draft.update(dict.fromkeys(locked))
            await session.execute(insert(WorkstreamTask).values(**draft))
            await session.execute(update(WorkstreamTask).where(WorkstreamTask.id == task_id).values(
                **locked, status="screening",
            ))
            await session.execute(update(WorkstreamTask).where(WorkstreamTask.id == task_id).values(
                status="in_progress", assigned_to=assignment["contributor_id"],
            ))
            await session.execute(insert(TaskAssignment).values(**(assignment | {
                "id": assignment_id, "task_id": task_id, "started_at": None,
            })))
            await session.execute(update(TaskAssignment).where(TaskAssignment.id == assignment_id).values(
                started_at=assignment["assigned_at"],
            ))
            expected.add(assignment_id)
    return expected


async def test_replay_does_not_publish_or_backfill(task_client, monkeypatch):
    from tests.test_tasks import auth_headers, set_dev_actor

    s = await setup_assignment(task_client, monkeypatch)
    set_dev_actor(monkeypatch, roles="project_manager", subject="project-manager-subject")
    headers = auth_headers()
    path = f"/api/v1/projects/{s.project['id']}/role-grants/{s.grant['grant_id']}/revoke"
    first = await task_client.post(path, headers=headers, json={"reason": "Exact origin"})
    assert first.status_code == 200, first.text
    async with s.sessions() as session:
        before = (await session.execute(select(OutboxEvent.__table__))).mappings().all()
    replay = await task_client.post(path, headers=headers, json={"reason": "Exact origin"})
    assert replay.status_code == 200 and replay.json() == first.json()
    async with s.sessions() as session:
        after = (await session.execute(select(OutboxEvent.__table__))).mappings().all()
    assert len(before) == 1 and before == after


async def test_reactivation_publishes_nothing(task_client, monkeypatch):
    from tests.test_tasks import auth_headers, set_dev_actor

    s = await setup_assignment(task_client, monkeypatch)
    await revoke(s, "suspend")
    async with s.sessions() as session:
        before = (await session.execute(select(OutboxEvent.__table__))).mappings().all()
    set_dev_actor(monkeypatch, roles="viewer", issuer=s.admin_identity[0], subject=s.admin_identity[1])
    response = await task_client.post(
        f"/api/v1/actors/{s.grant['actor_profile_id']}/reactivate",
        headers=auth_headers(), json={"reason": "Authority restored"},
    )
    assert response.status_code == 200, response.text
    async with s.sessions() as session:
        after = (await session.execute(select(OutboxEvent.__table__))).mappings().all()
    assert len(before) == 1 and before == after


@pytest.mark.parametrize("kind", ["grant", "link"])
async def test_publication_failure_is_sanitized_and_same_key_can_retry(task_client, monkeypatch, kind):
    from app.modules.outbox.api import OutboxPersistenceError
    from app.modules.outbox.service import OutboxService
    from app.modules.tasks.models import AuditEvent
    from tests.test_tasks import auth_headers, set_dev_actor

    s = await setup_assignment(task_client, monkeypatch)
    set_dev_actor(monkeypatch, roles="project_manager", subject="project-manager-subject")
    path = f"/api/v1/projects/{s.project['id']}/role-grants/{s.grant['grant_id']}/revoke"
    if kind == "link":
        set_dev_actor(monkeypatch, roles="viewer", issuer=s.admin_identity[0], subject=s.admin_identity[1])
        path = f"/api/v1/actor-identity-links/{s.link_id}/revoke"
    async with s.sessions() as session:
        before = set((await session.scalars(select(AuditEvent.id))).all())
    original = OutboxService.append
    calls = []

    async def failed(_owner, value):
        calls.append(value.aggregate_id)
        raise OutboxPersistenceError("private failed statement")

    headers = auth_headers()
    monkeypatch.setattr(OutboxService, "append", failed)
    response = await task_client.post(path, headers=headers, json={"reason": "Atomic failure"})
    assert response.status_code == 503, response.text
    assert "private failed statement" not in response.text
    assert calls == [UUID(s.assignment["id"])]
    async with s.sessions() as session:
        assert (await session.scalars(select(OutboxEvent))).all() == []
        assert set((await session.scalars(select(AuditEvent.id))).all()) == before
    monkeypatch.setattr(OutboxService, "append", original)
    response = await task_client.post(path, headers=headers, json={"reason": "Atomic failure"})
    assert response.status_code == 200, response.text
    async with s.sessions() as session:
        assert len((await session.scalars(select(OutboxEvent))).all()) == 1


async def test_project_revoke_is_scoped_and_actor_loss_spans_projects(task_client, monkeypatch):
    from tests.test_tasks import (
        create_active_project, create_ready_task, admit_and_grant_project_submitter,
        set_dev_actor, auth_headers,
    )
    s = await setup_assignment(task_client, monkeypatch)
    set_dev_actor(monkeypatch, roles="project_manager", subject="project-manager-subject")
    other_project = await create_active_project(task_client, slug="invalidation-other-project")
    task = await create_ready_task(task_client, other_project["id"])
    grant = await admit_and_grant_project_submitter(task_client, monkeypatch, other_project["id"], "invalidation-submitter")
    assert grant["actor_profile_id"] == s.grant["actor_profile_id"]
    claimed = await task_client.post(f"/api/v1/tasks/{task['id']}/claim", headers=auth_headers())
    assert claimed.status_code == 200, claimed.text
    other_assignment = UUID(claimed.json()["assignment"]["id"])
    await revoke(s, "grant")
    grant_cause = s.invalidation_id
    async with s.sessions() as session:
        events = (await session.scalars(select(OutboxEvent))).all()
        assert [(event.project_id, event.aggregate_id) for event in events] == [(s.project["id"], UUID(s.assignment["id"]))]
    await revoke(s, "suspend")
    async with s.sessions() as session:
        events = (await session.scalars(select(OutboxEvent))).all()
    assert len(events) == 3
    assert len([event for event in events if event.causation_event_id == grant_cause]) == 1
    assert {(event.project_id, event.aggregate_id) for event in events if event.causation_event_id == s.invalidation_id} == {
        (s.project["id"], UUID(s.assignment["id"])), (other_project["id"], other_assignment),
    }


async def test_reviewer_revoke_does_not_publish_submitter_assignments(task_client, monkeypatch):
    from app.adapters.auth.assignment_invalidation_publication import AssignmentInvalidationPublication
    from tests.test_tasks import auth_headers, set_dev_actor
    s = await setup_assignment(task_client, monkeypatch)
    set_dev_actor(monkeypatch, roles="project_manager", subject="project-manager-subject")
    unavailable = {"availability": "unavailable", "reference_ids": [], "unavailable_reason": "no_record"}
    response = await task_client.post(f"/api/v1/projects/{s.project['id']}/role-grants",
        headers=auth_headers(), json={"target_actor_profile_id": s.grant["actor_profile_id"],
        "role": "reviewer", "qualification": {"skills_snapshot": unavailable,
            "reputation_snapshot": unavailable, "prior_project_work_refs": [], "external_expertise_refs": []},
        "reason": "Separate reviewer obligation"})
    assert response.status_code == 201, response.text
    reviewer = response.json()["id"]
    async def forbidden(_owner, _facts):
        pytest.fail("reviewer authority loss attempted assignment publication")
    monkeypatch.setattr(AssignmentInvalidationPublication, "publish", forbidden)
    response = await task_client.post(f"/api/v1/projects/{s.project['id']}/role-grants/{reviewer}/revoke",
        headers=auth_headers(), json={"reason": "Review assignment authority withdrawn"})
    assert response.status_code == 200, response.text
    async with s.sessions() as session:
        assert (await session.scalars(select(OutboxEvent))).all() == []
