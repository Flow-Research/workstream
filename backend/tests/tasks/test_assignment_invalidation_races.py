"""Independent PostgreSQL ordering at acceptance and real TASK invalidation boundaries."""

import asyncio
from app.core.identifiers import new_record_id

import pytest
from sqlalchemy import select, text

from auth_concurrency_support import wait_for_named_database_lock
from app.modules.outbox.api import DeliveryOptions, HandlerOutcome
from app.modules.outbox.delivery import OutboxDelivery
from app.modules.tasks.models import WorkstreamTask
from app.modules.tasks.repository import TaskRepository
from tests import test_tasks as task_fixtures
from tests.test_tasks import auth_headers
from tests.tasks.invalidation_support import setup_assignment, revoke, invoked, snapshot

task_client = task_fixtures.task_client
task_database_env = task_fixtures.task_database_env


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


async def _assert_intake_invalidation_rollback(s, envelope, monkeypatch):
    from app.modules.artifacts.intake.repository import SubmissionIntakeRepository

    async def intake_facts():
        async with s.sessions() as session:
            return (await session.execute(text("""
                SELECT o.state,o.lease_generation,o.failure_code,o.raw_sha256,o.raw_byte_count,
                       c.state,c.accounted_bytes,
                       (SELECT jsonb_agg(to_jsonb(e) ORDER BY e.id) FROM public.audit_events e)
                FROM public.submission_intake_operations o
                JOIN public.submission_source_charges c ON c.operation_id=o.id WHERE o.task_id=:task
            """), {"task": s.task["id"]})).one()

    before, intake = await snapshot(s), await intake_facts()
    terminal, reached = SubmissionIntakeRepository._terminal, []
    async def fail_after_terminal(repository, row, state, code):
        await terminal(repository, row, state, code)
        assert row.state == "cancelled" and row.failure_code == "submission_unavailable"
        reached.append(row.id)
        raise RuntimeError("after real intake cancellation")
    with monkeypatch.context() as patch:
        patch.setattr(SubmissionIntakeRepository, "_terminal", fail_after_terminal)
        with pytest.raises(RuntimeError, match="after real intake cancellation"):
            await s.handler(envelope)
    assert len(reached) == 1
    assert await snapshot(s) == before
    assert await intake_facts() == intake


async def _race_acceptance_and_invalidation(s, envelope, payload, headers, database_url, winner, monkeypatch):
    from app.modules.artifacts.intake.foreground_admission import ForegroundIntakeAdmission
    from app.modules.tasks.intake_custody import IntakeTaskCustody
    from tests.tasks.submission_dispatch.test_revision_expiry import _wait_for_staged_submission

    pre_done, begin_accept, held, release = (asyncio.Event() for _ in range(4))
    blocker_pid = []
    names = {kind: f"assignment-{kind}-{new_record_id().hex}" for kind in ("submission", "invalidation")}
    accept, stage = ForegroundIntakeAdmission.accept, ForegroundIntakeAdmission._accept_new
    intake_lock, invalidation_lock = IntakeTaskCustody.lock, TaskRepository.lock_project_task

    async def before_accept(owner, *args, **kwargs):
        pre_done.set()
        await asyncio.wait_for(begin_accept.wait(), 60)
        return await accept(owner, *args, **kwargs)

    async def staged(owner, session, *args, **kwargs):
        result = await stage(owner, session, *args, **kwargs)
        if winner == "submission":
            blocker_pid.append(await session.scalar(text("SELECT pg_backend_pid()")))
            held.set()
            await asyncio.wait_for(release.wait(), 60)
        return result

    async def named_intake(owner, *args, **kwargs):
        if begin_accept.is_set() and asyncio.current_task().get_name().startswith("submission-foreground:"):
            await owner._session.execute(text("SELECT set_config('application_name',:name,true)"),
                                         {"name": names["submission"]})
        return await intake_lock(owner, *args, **kwargs)

    async def named_invalidation(owner, *args, **kwargs):
        if asyncio.current_task().get_name() != names["invalidation"]:
            return await invalidation_lock(owner, *args, **kwargs)
        await owner._session.execute(text("SELECT set_config('application_name',:name,true)"),
                                     {"name": names["invalidation"]})
        result = await invalidation_lock(owner, *args, **kwargs)
        if winner == "invalidation":
            blocker_pid.append(await owner._session.scalar(text("SELECT pg_backend_pid()")))
            held.set()
            await asyncio.wait_for(release.wait(), 60)
        return result

    with monkeypatch.context() as patch:
        patch.setattr(ForegroundIntakeAdmission, "accept", before_accept)
        patch.setattr(ForegroundIntakeAdmission, "_accept_new", staged)
        patch.setattr(IntakeTaskCustody, "lock", named_intake)
        patch.setattr(TaskRepository, "lock_project_task", named_invalidation)
        submitting = asyncio.create_task(s.client.post(
            f"/api/v1/tasks/{s.task['id']}/submissions", headers=headers, content=payload))
        invalidating = None
        try:
            await _wait_for_staged_submission(pre_done, submitting, timeout=90)
            if winner == "submission":
                begin_accept.set()
                await _wait_for_staged_submission(held, submitting, timeout=60)
                invalidating = asyncio.create_task(s.handler(envelope), name=names["invalidation"])
            else:
                await _assert_intake_invalidation_rollback(s, envelope, monkeypatch)
                invalidating = asyncio.create_task(s.handler(envelope), name=names["invalidation"])
                await _wait_for_staged_submission(held, invalidating, timeout=60)
                begin_accept.set()
            loser = "invalidation" if winner == "submission" else "submission"
            await asyncio.wait_for(wait_for_named_database_lock(
                database_url, names[loser], expected_blocker_pid=blocker_pid[0]), 30)
            release.set()
            return await asyncio.wait_for(asyncio.gather(
                submitting, invalidating, return_exceptions=True), 90)
        finally:
            begin_accept.set()
            release.set()
            pending = [job for job in (submitting, invalidating) if job is not None]
            for job in pending:
                if not job.done():
                    job.cancel()
            await asyncio.gather(*pending, return_exceptions=True)


@pytest.mark.parametrize("winner", ["submission", "invalidation"])
async def test_real_submission_and_invalidation_serialize(
    task_client, task_database_env, monkeypatch, tmp_path, winner,
):
    from types import SimpleNamespace
    from uuid import UUID
    from app.modules.artifacts.intake.models import SubmissionIntakeOperation
    from app.modules.tasks.models import Submission
    from tests.artifacts.test_submission_foreground_command import configure_source_http
    from tests.retained_material_fixtures import finalize_retained_intake
    from tests.tasks.invalidation_support import submission_packet
    from tests.test_artifact_admission import _settings, _namespace, _local_store
    from tests.test_tasks import set_dev_actor

    settings = _settings(tmp_path, maximum_bytes=1024 * 1024)
    s = await setup_assignment(task_client, monkeypatch, artifact_settings=settings)
    payload, headers = await submission_packet(s)
    await revoke(s, "suspend")
    restored = await s.client.post(
        f"/api/v1/actors/{s.grant['actor_profile_id']}/reactivate",
        headers=auth_headers(), json={"reason": "Allow submission to compete with pending invalidation"})
    assert restored.status_code == 200, restored.text
    _, envelope = await invoked(s)
    set_dev_actor(monkeypatch, roles="project_submitter", subject="invalidation-submitter")
    _, settings, errors, calls = await configure_source_http(
        s.sessions, s.client, tmp_path, monkeypatch, payload, "completed")
    headers |= auth_headers()
    response, invalidated = await _race_acceptance_and_invalidation(
        s, envelope, payload, headers, task_database_env, winner, monkeypatch)
    assert invalidated is HandlerOutcome.ACKNOWLEDGE, repr(invalidated)
    assert len(calls) == 1 and errors == [], errors
    task, assignments, events = await snapshot(s)
    releases = [row for row in events if row["event_type"] == "TaskAssignmentAuthorityRevoked"]
    async with s.sessions() as session:
        operations = (await session.scalars(select(SubmissionIntakeOperation).where(
            SubmissionIntakeOperation.task_id == s.task["id"]))).all()
        assert len(operations) == 1
        operation = operations[0]
        assert (await session.scalars(select(Submission).where(
            Submission.task_id == s.task["id"]))).all() == []
        assert operation.finalized_submission_id is None
        charge = (await session.execute(text("""
            SELECT accounted_bytes, state FROM public.submission_source_charges
            WHERE operation_id=:id
        """), {"id": operation.id})).one()
        assert charge == (len(payload), "sealed")
    if winner == "submission":
        assert response.status_code == 202, response.text
        assert operation.state == "finalization_pending"
        assert response.json()["operation_id"] == str(operation.id)
        assert task["status"] == "evaluation_pending"
        assert assignments[0]["status"] == "active" and assignments[0]["released_at"] is None
        assert releases == []
        namespace = _namespace(settings)
        bootstrap, store = _local_store(settings, namespace)
        try:
            submission_id = await finalize_retained_intake(s.sessions, SimpleNamespace(
                operation_id=UUID(response.json()["operation_id"]), store=store,
                namespace=namespace, settings=settings))
        finally:
            bootstrap.close()
        async with s.sessions() as session:
            facts = (await session.execute(text("""
                SELECT s.task_assignment_id::text, a.status, a.consumed_by_submission_id::text,
                       public.submission_dispatch_valid(d)
                FROM public.submissions s JOIN public.submission_bundle_admissions a
                  ON a.id=s.submission_bundle_admission_id
                JOIN public.submission_dispatches d ON d.submission_id=s.id WHERE s.id=:id
            """), {"id": submission_id})).one()
            assert facts == (s.assignment["id"], "consumed", str(submission_id), True)
    else:
        assert response.status_code == 404, response.text
        assert response.json()["error"]["code"] == "submission_unavailable"
        assert operation.acceptance_receipt is None and operation.finalization_event_id is None
        assert operation.state == "cancelled" and operation.lease_generation == 2
        assert operation.failure_code == "submission_unavailable"
        assert task["status"] == "ready" and task["assigned_to"] is None
        assert task["active_submission_operation_id"] is None
        assert assignments[0]["status"] == "authority_revoked" and assignments[0]["released_at"] is not None
        assert len(releases) == 1
        replay = await s.client.post(f"/api/v1/tasks/{s.task['id']}/submissions", headers=headers, content=payload)
        assert replay.status_code == 404 and replay.json()["error"]["code"] == "submission_unavailable"
        before = await snapshot(s)
        assert await s.handler(envelope) is HandlerOutcome.ACKNOWLEDGE
        assert await snapshot(s) == before
        assert len(calls) == 1


async def test_invalidation_during_receiving_retains_charge_and_replays_without_body(
    task_client, task_database_env, monkeypatch, tmp_path,
):
    from tests.artifacts.test_submission_foreground_command import configure_source_http
    from tests.tasks.invalidation_support import submission_packet
    from tests.tasks.submission_dispatch.test_revision_expiry import _wait_for_staged_submission
    from tests.test_artifact_admission import _settings
    from tests.test_tasks import set_dev_actor

    settings = _settings(tmp_path, maximum_bytes=1024 * 1024)
    s = await setup_assignment(task_client, monkeypatch, artifact_settings=settings)
    payload, headers = await submission_packet(s)
    await revoke(s, "suspend")
    restored = await s.client.post(
        f"/api/v1/actors/{s.grant['actor_profile_id']}/reactivate", headers=auth_headers(),
        json={"reason": "Exercise receiving intake against committed release cause"})
    assert restored.status_code == 200, restored.text
    _, envelope = await invoked(s)
    set_dev_actor(monkeypatch, roles="project_submitter", subject="invalidation-submitter")
    _, _, errors, calls = await configure_source_http(
        s.sessions, s.client, tmp_path, monkeypatch, payload, "completed")
    headers |= auth_headers() | {"Content-Length": str(len(payload))}
    receiving, release = asyncio.Event(), asyncio.Event()

    async def held_body():
        receiving.set()
        await release.wait()
        yield payload

    async def forbidden_body():
        pytest.fail("known unsealed assignment cancellation consumed replay body")
        yield b"unreachable"

    async def facts():
        async with s.sessions() as session:
            return (await session.execute(text("""
                SELECT o.id::text,o.state,o.lease_generation,o.failure_code,o.raw_sha256,
                       o.raw_byte_count,o.acceptance_receipt,o.finalization_event_id,
                       c.state,c.accounted_bytes,
                       (SELECT count(*) FROM public.submissions WHERE task_id=:task),
                       (SELECT count(*) FROM public.selected_pre_submit_runs WHERE task_id=:task)
                FROM public.submission_intake_operations o
                JOIN public.submission_source_charges c ON c.operation_id=o.id WHERE o.task_id=:task
            """), {"task": s.task["id"]})).one()

    route = f"/api/v1/tasks/{s.task['id']}/submissions"
    request = asyncio.create_task(s.client.post(route, headers=headers, content=held_body()))
    try:
        await _wait_for_staged_submission(receiving, request, timeout=90)
        before = await facts()
        assert before[1:4] == ("receiving", 1, None)
        assert await s.handler(envelope) is HandlerOutcome.ACKNOWLEDGE
        release.set()
        response = await asyncio.wait_for(request, 60)
    finally:
        release.set()
        if not request.done():
            request.cancel()
        await asyncio.gather(request, return_exceptions=True)
    assert response.status_code == 404 and response.json()["error"]["code"] == "submission_unavailable"
    after = await facts()
    assert after == (before[0], "cancelled", 2, "submission_unavailable", None, None,
                     None, None, "reserved", len(payload), 0, 0)
    replay = await s.client.post(route, headers=headers, content=forbidden_body())
    assert replay.status_code == 404 and replay.json()["error"]["code"] == "submission_unavailable"
    progress = await s.client.get(f"/api/v1/tasks/{s.task['id']}/submission-operations",
                                  headers=auth_headers(), params={"operation_id": before[0]})
    assert progress.status_code == 200, progress.text
    assert progress.json()["failure_code"] == "submission_unavailable"
    assert progress.json()["operation_state"] == "cancelled"
    assert await facts() == after
    assert calls == [] and errors == []
    task, assignments, events = await snapshot(s)
    assert task["status"] == "ready" and task["active_submission_operation_id"] is None
    assert assignments[0]["status"] == "authority_revoked"
    assert len([event for event in events if event["event_type"] == "TaskAssignmentAuthorityRevoked"]) == 1
