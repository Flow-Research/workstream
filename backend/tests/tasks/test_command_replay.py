"""Real task retries preserve authority, atomicity and immutable result custody."""

import asyncio
import json
from copy import deepcopy
from uuid import UUID, uuid4

import pytest
from auth_concurrency_support import wait_for_named_database_lock
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm.attributes import set_committed_value

from app.adapters.artifacts import task_guide_documents_port
from app.adapters.audit import task_transition_audit
from app.adapters.tasks import task_service
from app.core.config import get_settings
from app.core.identifiers import new_record_id
from app.db import session as db_session
from app.modules.actors.models import ActorIdentityLink, ActorProfile
from app.modules.authorization.task_authorization import PreparedTaskAuthorization
from app.modules.tasks.authorized_commands import AuthorizedTaskCommands
from app.modules.tasks.command_replay import TaskCommandReplay
from app.modules.tasks.models import AuditEvent, TaskAssignment, TaskCommandReceipt, WorkstreamTask
from tests.authorization.task_authority.test_concurrency import actor_context
from tests.test_tasks import (
    task_client as task_client, task_database_env as task_database_env,
    admit_and_grant_project_submitter, auth_headers, create_active_project, create_ready_task, set_dev_actor,
)


async def _setup(client, monkeypatch):
    project = await create_active_project(client)
    task = await create_ready_task(client, project["id"])
    grant = await admit_and_grant_project_submitter(client, monkeypatch, project["id"], "retry-submitter")
    return project, task, grant


async def _counts(task_id):
    async with db_session.get_session_factory()() as session:
        return tuple([await session.scalar(select(func.count()).select_from(model).where(predicate))
                      for model, predicate in (
                          (TaskAssignment, TaskAssignment.task_id == task_id),
                          (TaskCommandReceipt, (TaskCommandReceipt.task_id == task_id) &
                           TaskCommandReceipt.action_id.in_(("task.claim", "task.start", "operations.task.start_override"))),
                          (AuditEvent, (AuditEvent.entity_id == task_id) &
                           AuditEvent.event_type.in_(("TaskClaimed", "TaskStarted", "TaskStartOverridden"))),
                      )])


async def test_committed_task_response_replays_once(task_client, monkeypatch):
    _, task, _ = await _setup(task_client, monkeypatch)
    headers = auth_headers()
    path = f"/api/v1/tasks/{task['id']}/claim"
    first = await task_client.post(path, headers=headers, json={"reason": "Exact request"})
    assert first.status_code == 200, first.text
    before = await _counts(task["id"])
    replayed = await task_client.post(path, headers=headers, json={"reason": "Exact request"})
    assert replayed.status_code == 200, replayed.text
    assert replayed.json() == first.json()
    assert await _counts(task["id"]) == before == (1, 1, 1)
    async with db_session.get_session_factory()() as session:
        receipt = await session.scalar(select(TaskCommandReceipt).where(
            TaskCommandReceipt.idempotency_key == UUID(headers["Idempotency-Key"]),
        ))
        assert receipt.status == "committed" and receipt.assignment_id
        decisions = list(await session.scalars(select(AuditEvent).where(AuditEvent.action_id == "task.claim")))
        assert len(decisions) == 2 and all(row.after_facts["allowed"] for row in decisions)


async def test_task_key_mismatch_rejects_reason_and_target(task_client, monkeypatch):
    project = await create_active_project(task_client)
    first_task = await create_ready_task(task_client, project["id"])
    other_task = await create_ready_task(task_client, project["id"])
    await admit_and_grant_project_submitter(task_client, monkeypatch, project["id"], "retry-submitter")
    headers = auth_headers()
    first = await task_client.post(f"/api/v1/tasks/{first_task['id']}/claim", headers=headers, json={"reason": "first"})
    assert first.status_code == 200, first.text
    for target, reason in ((first_task, "changed"), (other_task, "first")):
        conflict = await task_client.post(f"/api/v1/tasks/{target['id']}/claim", headers=headers, json={"reason": reason})
        assert conflict.status_code == 409, conflict.text
        assert conflict.json()["error"]["code"] == "idempotency_mismatch"
    assert await _counts(first_task["id"]) == (1, 1, 1)
    assert await _counts(other_task["id"]) == (0, 0, 0)


async def test_task_key_namespace_is_per_actor(task_client, monkeypatch):
    project = await create_active_project(task_client)
    first = await create_ready_task(task_client, project["id"])
    second = await create_ready_task(task_client, project["id"])
    headers = auth_headers()
    for subject, task in (("first-retry-actor", first), ("second-retry-actor", second)):
        await admit_and_grant_project_submitter(task_client, monkeypatch, project["id"], subject)
        result = await task_client.post(f"/api/v1/tasks/{task['id']}/claim", headers=headers)
        assert result.status_code == 200, result.text
    denied = await task_client.post(f"/api/v1/tasks/{first['id']}/claim", headers=headers)
    assert denied.status_code == 403, denied.text
    assert await _counts(first["id"]) == await _counts(second["id"]) == (1, 1, 1)


@pytest.mark.parametrize("target", ["task", "assignment", "locked_context", "historical_claimed", "task_size"])
async def test_validly_shaped_snapshot_cannot_substitute_identity(task_client, monkeypatch, target):
    _, task, _ = await _setup(task_client, monkeypatch)
    headers = auth_headers()
    path = f"/api/v1/tasks/{task['id']}/claim"
    first = await task_client.post(path, headers=headers)
    assert first.status_code == 200, first.text
    original = TaskCommandReplay.recover
    async def substituted(owner, receipt, *args, **kwargs):
        # Simulate corrupted in-memory custody without relying on DB triggers
        # to reject it first: the application identity assertion must catch it.
        if target == "locked_context":
            set_committed_value(receipt, "locked_context_hash", "sha256:" + "0" * 64)
        else:
            snapshot = deepcopy(receipt.response)
            if target == "task_size":
                snapshot["task"]["task_size"] = "large"
            elif target == "historical_claimed":
                snapshot["task"]["status"] = "claimed"
            else:
                snapshot[target]["id"] = str(uuid4())
            set_committed_value(receipt, "response", snapshot)
        return await original(owner, receipt, *args, **kwargs)
    with monkeypatch.context() as patch:
        patch.setattr(TaskCommandReplay, "recover", substituted)
        rejected = await task_client.post(path, headers=headers)
    assert rejected.status_code == 409, rejected.text
    assert rejected.json()["error"]["code"] == "task_replay_state_changed"
    control = await task_client.post(path, headers=headers)
    assert control.status_code == 200 and control.json() == first.json()


@pytest.mark.parametrize("transition", ["suspend", "revoke_link", "revoke_grant"])
async def test_replay_rechecks_current_authority(task_client, monkeypatch, transition):
    project, task, grant = await _setup(task_client, monkeypatch)
    headers = auth_headers()
    path = f"/api/v1/tasks/{task['id']}/claim"
    first = await task_client.post(path, headers=headers)
    assert first.status_code == 200, first.text
    before = await _counts(task["id"])
    assert before == (1, 1, 1)
    if transition == "revoke_grant":
        set_dev_actor(monkeypatch, roles="project_manager", subject="project-manager-subject")
        revoked = await task_client.post(
            f"/api/v1/projects/{project['id']}/role-grants/{grant['grant_id']}/revoke",
            headers=auth_headers(), json={"reason": "Revoke before retry"},
        )
        assert revoked.status_code == 200, revoked.text
        set_dev_actor(monkeypatch, roles="viewer", subject="retry-submitter")
    else:
        async with db_session.get_session_factory()() as session, session.begin():
            if transition == "suspend":
                profile = await session.get(ActorProfile, grant["actor_profile_id"])
                profile.status, profile.suspended_by = "suspended", profile.id
                profile.suspended_at, profile.suspension_reason = func.now(), "Suspend before retry"
            else:
                link = await session.scalar(select(ActorIdentityLink).where(
                    ActorIdentityLink.actor_profile_id == grant["actor_profile_id"],
                ))
                link.status, link.revoked_by = "revoked", grant["actor_profile_id"]
                link.revoked_at, link.revoked_reason = func.now(), "Revoke before retry"
    denied = await task_client.post(path, headers=headers)
    assert denied.status_code == 403, denied.text
    assert "assignment" not in denied.json()
    assert await _counts(task["id"]) == before


async def test_same_key_independent_sessions_have_one_result(task_client, task_database_env, monkeypatch):
    _, task, grant = await _setup(task_client, monkeypatch)
    context = await actor_context(grant["actor_profile_id"])
    key = uuid4()
    locked, release = asyncio.Event(), asyncio.Event()
    waiter_name = f"task-retry-{uuid4().hex}"
    original = TaskCommandReplay.reserve
    async def observe_reservation(owner, *args):
        is_waiter = asyncio.current_task().get_name() == waiter_name
        if is_waiter:
            await owner._session.execute(text("select set_config('application_name', :name, true)"),
                                         {"name": waiter_name})
        result = await original(owner, *args)
        if not is_waiter:
            locked.set()
            await release.wait()
        return result
    monkeypatch.setattr(TaskCommandReplay, "reserve", observe_reservation)
    async def claim():
        async with db_session.get_session_factory()() as session:
            command = AuthorizedTaskCommands(
                session, authorization=PreparedTaskAuthorization(session, context),
                audit=task_transition_audit(session), actor_profile_id=context.actor_profile_id,
                contexts=task_service(session, settings=get_settings()),
                guide_documents=task_guide_documents_port(session, get_settings()),
            )
            return await command.claim(UUID(task["id"]), "same request", idempotency_key=key)
    pending = [asyncio.create_task(claim())]
    try:
        await asyncio.wait_for(locked.wait(), timeout=30)
        pending.append(asyncio.create_task(claim(), name=waiter_name))
        await asyncio.wait_for(wait_for_named_database_lock(task_database_env, waiter_name), timeout=30)
        assert not pending[1].done()
        release.set()
        first, second = await asyncio.wait_for(asyncio.gather(*pending), timeout=30)
    finally:
        release.set()
        for running in pending:
            if not running.done():
                running.cancel()
        await asyncio.gather(*pending, return_exceptions=True)
    assert first.model_dump(mode="json") == second.model_dump(mode="json")
    assert await _counts(task["id"]) == (1, 1, 1)


async def test_receipt_sql_shape_and_assignment_ownership(task_client, monkeypatch):
    project = await create_active_project(task_client)
    first = await create_ready_task(task_client, project["id"])
    second = await create_ready_task(task_client, project["id"])
    grant = await admit_and_grant_project_submitter(task_client, monkeypatch, project["id"], "receipt-owner")
    claimed = await task_client.post(f"/api/v1/tasks/{first['id']}/claim", headers=auth_headers())
    assert claimed.status_code == 200, claimed.text
    assignment_id = claimed.json()["assignment"]["id"]
    async with db_session.get_session_factory()() as session:
        original_response = await session.scalar(select(TaskCommandReceipt.response).where(
            TaskCommandReceipt.task_id == first["id"],
            TaskCommandReceipt.assignment_id == assignment_id,
        ))
    # Keep unrelated size custody valid so each probe reaches its intended
    # assignment/action/state constraint rather than the earlier size guard.
    values = {
        "receipt_id": new_record_id(), "idempotency_key": new_record_id(),
        "actor": grant["actor_profile_id"], "task": first["id"], "assignment": assignment_id,
        "contributor": grant["actor_profile_id"], "status": "committed", "action": "task.claim",
        "digest": "sha256:" + "0" * 64, "response": json.dumps(original_response),
    }
    statement = text("""insert into task_command_receipts
        (id, actor_profile_id, action_id, idempotency_key, request_digest, task_id,
         status, assignment_id, contributor_id, locked_context_hash, response, committed_at)
        values (:receipt_id, :actor, :action, :idempotency_key, :digest, :task,
                :status, :assignment, :contributor, :digest, CAST(:response AS jsonb), now())""")
    for changes, constraint in (
        ({"task": second["id"]}, "fk_task_command_assignment"),
        ({"contributor": str(uuid4())}, "task_command_contributor"),
        ({"status": "pending"}, "task_command_state_shape"),
        ({"action": "task.unknown"}, "task_command_action"),
        ({"digest": "invalid"}, "task_command_request_digest"),
    ):
        parameters = {**values, **changes}
        if parameters["action"] != "task.claim":
            parameters["response"] = json.dumps(original_response["task"])
        async with db_session.get_session_factory()() as session:
            with pytest.raises(IntegrityError, match=constraint):
                await session.execute(statement, parameters)
            await session.rollback()
    assert await _counts(first["id"]) == (1, 1, 1)
    assert await _counts(second["id"]) == (0, 0, 0)
    # The actor FK remains enforced at commit, without an early KEY SHARE.
    async with db_session.get_session_factory()() as session:
        constraint = (await session.execute(text("""select condeferrable, condeferred
            from pg_constraint where conrelid='task_command_receipts'::regclass
            and confrelid='actor_profiles'::regclass"""))).one()
        assert tuple(constraint) == (True, True)
        await session.execute(text("""insert into task_command_receipts
            (id, actor_profile_id, action_id, idempotency_key, request_digest, task_id, status)
            values(:receipt_id, :actor, 'task.claim', :idempotency_key, :digest, :task, 'pending')"""),
            {
                **values,
                "receipt_id": new_record_id(),
                "idempotency_key": new_record_id(),
                "actor": str(uuid4()),
            })
        with pytest.raises(IntegrityError, match="actor_profile_id"):
            await session.commit()
        await session.rollback()


async def test_receipt_failure_rolls_back_and_retry_succeeds(task_client, monkeypatch):
    _, task, _ = await _setup(task_client, monkeypatch)
    before = await _counts(task["id"])
    assert before == (0, 0, 0)
    headers = auth_headers()
    path = f"/api/v1/tasks/{task['id']}/claim"
    original = TaskCommandReplay.complete
    def fail_after_staging(*args):
        original(*args)
        raise OperationalError("receipt failure", None, RuntimeError("injected"))
    with monkeypatch.context() as patch:
        patch.setattr(TaskCommandReplay, "complete", staticmethod(fail_after_staging))
        failed = await task_client.post(path, headers=headers)
    assert failed.status_code == 503, failed.text
    assert await _counts(task["id"]) == before
    async with db_session.get_session_factory()() as session:
        row = await session.get(WorkstreamTask, task["id"])
        assert row.status == "ready"
        assert row.assigned_to is None
        assert await session.scalar(select(func.count()).select_from(AuditEvent).where(
            AuditEvent.action_id == "task.claim",
        )) == 0
    retried = await task_client.post(path, headers=headers)
    assert retried.status_code == 200, retried.text
    assert await _counts(task["id"]) == (1, 1, 1)


async def test_same_actor_distinct_receipts_do_not_invert_authority_locks(task_client, monkeypatch):
    project = await create_active_project(task_client)
    tasks = [await create_ready_task(task_client, project["id"]) for _ in range(2)]
    grant = await admit_and_grant_project_submitter(task_client, monkeypatch, project["id"], "parallel-submitter")
    context = await actor_context(grant["actor_profile_id"])
    reserved = asyncio.Barrier(2)
    original = TaskCommandReplay.reserve
    async def both_reserved(owner, *args):
        result = await original(owner, *args)
        await reserved.wait()
        return result
    monkeypatch.setattr(TaskCommandReplay, "reserve", both_reserved)
    async def claim(task):
        async with db_session.get_session_factory()() as session:
            command = AuthorizedTaskCommands(
                session, authorization=PreparedTaskAuthorization(session, context),
                audit=task_transition_audit(session), actor_profile_id=context.actor_profile_id,
                contexts=task_service(session, settings=get_settings()),
                guide_documents=task_guide_documents_port(session, get_settings()),
            )
            return await command.claim(UUID(task["id"]), idempotency_key=uuid4())
    results = await asyncio.wait_for(asyncio.gather(*(claim(task) for task in tasks)), timeout=30)
    assert {result.task.id for result in results} == {task["id"] for task in tasks}
    for task in tasks:
        assert await _counts(task["id"]) == (1, 1, 1)


@pytest.mark.parametrize("key", [None, "invalid", "duplicate"])
async def test_task_key_validated_before_provisioning(task_client, monkeypatch, key):
    set_dev_actor(monkeypatch, roles="viewer", subject="must-not-provision")
    async with db_session.get_session_factory()() as session:
        before = await session.scalar(select(func.count()).select_from(ActorProfile))
    headers = [("Authorization", "Bearer task-token")]
    if key is not None:
        headers += [("Idempotency-Key", str(uuid4()) if key == "duplicate" else key)]
    if key == "duplicate":
        headers += [("Idempotency-Key", str(uuid4()))]
    result = await task_client.post(f"/api/v1/tasks/{uuid4()}/claim", headers=headers, json={"reason": "test"})
    assert result.status_code == 422, result.text
    async with db_session.get_session_factory()() as session:
        assert await session.scalar(select(func.count()).select_from(ActorProfile)) == before


async def test_committed_receipt_is_immutable_through_sql(task_client, monkeypatch):
    _, task, _ = await _setup(task_client, monkeypatch)
    response = await task_client.post(f"/api/v1/tasks/{task['id']}/claim", headers=auth_headers())
    assert response.status_code == 200, response.text
    async with db_session.get_session_factory()() as session:
        retained = (await session.execute(text(
            "select to_jsonb(r)::text from task_command_receipts r order by id"
        ))).scalars().all()
    statements = (
        "update task_command_receipts set idempotency_key=gen_random_uuid()",
        "update task_command_receipts set task_id='" + str(uuid4()) + "'",
        "update task_command_receipts set response='{}'::jsonb",
        "update task_command_receipts set request_digest='sha256:'||repeat('0',64)",
        "delete from task_command_receipts", "truncate task_command_receipts cascade",
    )
    for statement in statements:
        async with db_session.get_session_factory()() as session:
            with pytest.raises(IntegrityError, match="task command receipt"):
                await session.execute(text(statement))
            await session.rollback()
            assert (await session.execute(text(
                "select to_jsonb(r)::text from task_command_receipts r order by id"
            ))).scalars().all() == retained
    async with db_session.get_session_factory()() as session, session.begin():
        assert (await session.execute(text("update task_command_receipts set id=id"))).rowcount == 4
    assert await _counts(task["id"]) == (1, 1, 1)
