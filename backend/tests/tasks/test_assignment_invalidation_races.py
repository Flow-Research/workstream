"""Independent PostgreSQL ordering at the hidden effect and real TASK boundaries."""

import asyncio
from app.core.identifiers import new_record_id

import pytest
from sqlalchemy import select, text

from auth_concurrency_support import wait_for_named_database_lock
from app.modules.outbox.api import DeliveryOptions, HandlerOutcome
from app.modules.outbox.delivery import OutboxDelivery
from app.modules.tasks.models import WorkstreamTask
from app.modules.tasks.repository import TaskRepository
from tests.test_tasks import (
    task_client as task_client,
    task_database_env as task_database_env,
    auth_headers,
)
from tests.tasks.invalidation_support import setup_assignment, revoke, invoked, snapshot


async def test_expired_delivery_waiting_for_task_cannot_release(
    task_client, task_database_env, monkeypatch
):
    s = await setup_assignment(task_client, monkeypatch)
    await revoke(s)
    s.h.options = DeliveryOptions(lease_seconds=30, handler_timeout_seconds=25)
    s.h.delivery = s.h.build(s.h.delivery._registry)
    _, envelope = await invoked(s)
    before = await snapshot(s)
    observed = asyncio.Event()
    original_observe = OutboxDelivery.observe_invocation
    original_lock = TaskRepository.lock_project_task
    waiter = "assignment-expiry-" + new_record_id().hex

    async def observe(owner, value):
        result = await original_observe(owner, value)
        assert result is not None, "positive committed precheck must happen before expiry"
        observed.set()
        return result

    async def named_lock(owner, *args):
        await owner._session.execute(
            text("select set_config('application_name', :name, true)"), {"name": waiter}
        )
        return await original_lock(owner, *args)

    monkeypatch.setattr(OutboxDelivery, "observe_invocation", observe)
    monkeypatch.setattr(TaskRepository, "lock_project_task", named_lock)
    pending = None
    try:
        async with s.sessions() as blocker, blocker.begin():
            await blocker.scalar(
                select(WorkstreamTask).where(WorkstreamTask.id == s.task["id"]).with_for_update()
            )
            pending = asyncio.create_task(s.handler(envelope), name=waiter)
            await asyncio.wait_for(observed.wait(), 30)
            await asyncio.wait_for(wait_for_named_database_lock(task_database_env, waiter), 30)
            await blocker.execute(
                text(
                    "select pg_sleep(greatest(0, extract(epoch from (cast(:expiry as timestamptz) - clock_timestamp()))) + 0.05)"
                ),
                {"expiry": envelope.claim.claim_expires_at},
            )
        assert await asyncio.wait_for(pending, 30) is HandlerOutcome.REJECT
    finally:
        if pending is not None:
            await asyncio.gather(pending, return_exceptions=True)
    assert await snapshot(s) == before
    assert [stage for stage, _ in s.trace] == ["prepare", "consume", "close"]


async def test_concurrent_events_for_same_cause_have_one_effect(task_client, monkeypatch):
    s = await setup_assignment(task_client, monkeypatch)
    await revoke(s)
    target, first = await invoked(s)
    _, second = await invoked(s, target=target, synthetic_transport=True)
    before = await snapshot(s)
    outcomes = await asyncio.wait_for(asyncio.gather(s.handler(first), s.handler(second)), 10)
    assert outcomes == [HandlerOutcome.ACKNOWLEDGE, HandlerOutcome.ACKNOWLEDGE]
    task, assignments, events = await snapshot(s)
    assert task["status"] == "ready" and task["assigned_to"] is None
    assert assignments[0]["status"] == "authority_revoked"
    assert len(events) == len(before[2]) + 1
    assert len(s.trace) == 3


async def test_restored_authority_does_not_cancel_pending_assignment_release(task_client, monkeypatch):
    """Restoring access does not revoke an already committed release cause."""
    s = await setup_assignment(task_client, monkeypatch)
    await revoke(s, "suspend")
    _, envelope = await invoked(s)
    restored = await s.client.post(
        f"/api/v1/actors/{s.grant['actor_profile_id']}/reactivate",
        headers=auth_headers(),
        json={"reason": "Restored access preserves pending assignment release"},
    )
    assert restored.status_code == 200, restored.text
    before = await snapshot(s)
    assert before[0]["status"] == "in_progress"
    assert await s.handler(envelope) is HandlerOutcome.ACKNOWLEDGE
    task, assignments, events = await snapshot(s)
    assert task["status"] == "ready" and task["assigned_to"] is None
    assert assignments[0]["status"] == "authority_revoked"
    releases = [row for row in events if row["event_type"] == "TaskAssignmentAuthorityRevoked"]
    assert len(releases) == 1 and releases[0]["from_status"] == "in_progress"
    assert len(events) == len(before[2]) + 1
    after = await snapshot(s)
    assert await s.handler(envelope) is HandlerOutcome.ACKNOWLEDGE
    assert await snapshot(s) == after


@pytest.mark.parametrize("winner", ["submission", "invalidation"])
async def test_real_submission_and_invalidation_serialize(
    task_client, task_database_env, monkeypatch, tmp_path, winner
):
    from app.api.deps.authorization import compose_hidden_submission_creation_command
    from app.modules.artifacts.models import SubmissionBundleAdmission
    from app.modules.tasks.api import TaskSubmissionContextUnavailable
    from app.modules.tasks.api.submission_command import SubmissionCreationResult
    from app.modules.tasks.models import Submission
    from tests.tasks.invalidation_support import prepare_submission

    from tests.test_artifact_admission import _settings

    settings = _settings(tmp_path, maximum_bytes=1024 * 1024)
    s = await setup_assignment(task_client, monkeypatch, artifact_settings=settings)
    context, creation = await prepare_submission(s, settings)
    await revoke(s, "suspend")
    restored = await s.client.post(
        f"/api/v1/actors/{s.grant['actor_profile_id']}/reactivate",
        headers=auth_headers(),
        json={"reason": "Allow real submission to compete with pending invalidation"},
    )
    assert restored.status_code == 200, restored.text
    _, envelope = await invoked(s)
    acquired, release = asyncio.Event(), asyncio.Event()
    names = {kind: f"assignment-{kind}-{new_record_id().hex}" for kind in ("submission", "invalidation")}
    loser = "invalidation" if winner == "submission" else "submission"
    original_get, original_lock = TaskRepository.get_task, TaskRepository.lock_project_task

    async def lock(owner, method, *args, **kwargs):
        name = asyncio.current_task().get_name()
        await owner._session.execute(
            text("select set_config('application_name', :name, true)"), {"name": name}
        )
        result = await method(owner, *args, **kwargs)
        if name == names[winner]:
            acquired.set()
            await asyncio.wait_for(release.wait(), 10)
        return result

    async def get_task(owner, *args, **kwargs):
        if kwargs.get("for_update"):
            return await lock(owner, original_get, *args, **kwargs)
        return await original_get(owner, *args, **kwargs)

    async def project_task(owner, *args, **kwargs):
        return await lock(owner, original_lock, *args, **kwargs)

    monkeypatch.setattr(TaskRepository, "get_task", get_task)
    monkeypatch.setattr(TaskRepository, "lock_project_task", project_task)

    async def submit():
        async with s.sessions() as session:
            return await compose_hidden_submission_creation_command(
                session,
                context,
                request_id=new_record_id(),
                correlation_id=new_record_id(),
            ).create(creation)

    calls = {"submission": submit, "invalidation": lambda: s.handler(envelope)}
    pending = []
    try:
        pending.append(asyncio.create_task(calls[winner](), name=names[winner]))
        await asyncio.wait_for(acquired.wait(), 10)
        pending.append(asyncio.create_task(calls[loser](), name=names[loser]))
        await asyncio.wait_for(wait_for_named_database_lock(task_database_env, names[loser]), 10)
        release.set()
        results = dict(
            zip(
                (winner, loser),
                await asyncio.wait_for(asyncio.gather(*pending, return_exceptions=True), 15),
            )
        )
    finally:
        release.set()
        await asyncio.gather(*pending, return_exceptions=True)
    assert results["invalidation"] is HandlerOutcome.ACKNOWLEDGE
    task, assignments, events = await snapshot(s)
    releases = [row for row in events if row["event_type"] == "TaskAssignmentAuthorityRevoked"]
    async with s.sessions() as session:
        submissions = (
            await session.scalars(select(Submission).where(Submission.task_id == s.task["id"]))
        ).all()
        admission = await session.get(SubmissionBundleAdmission, str(creation.admission_id))
        if winner == "submission":
            result = results["submission"]
            assert isinstance(result, SubmissionCreationResult), result
            assert len(submissions) == 1
            submission = submissions[0]
            assert submission.id == str(result.submission_id)
            assert submission.task_assignment_id == s.assignment["id"]
            assert submission.artifact_binding_id == str(result.artifact_binding_id)
            assert submission.artifact_content_id == str(result.artifact_content_id)
            assert admission.status == "consumed"
            assert admission.consumed_by_submission_id == submission.id
            assert task["status"] == "evaluation_pending"
            assert assignments[0]["status"] == "active" and assignments[0]["released_at"] is None
            assert not releases
        else:
            assert isinstance(results["submission"], TaskSubmissionContextUnavailable), results
            assert not submissions
            assert admission.status == "ready" and admission.consumed_by_submission_id is None
            assert task["status"] == "ready" and task["assigned_to"] is None
            assert assignments[0]["status"] == "authority_revoked"
            assert assignments[0]["released_at"] is not None
            assert len(releases) == 1
