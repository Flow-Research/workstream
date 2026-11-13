"""Independent SQL guards for pre-assignment command receipts."""

from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.core.identifiers import new_record_id
from app.db import session as db_session
from tests.test_tasks import (
    task_database_env as task_database_env,
    task_client as task_client,
    create_active_project,
    create_draft_task,
)


async def test_manager_receipt_rejects_unproven_sql_shape(task_client):
    project = await create_active_project(task_client)
    task = await create_draft_task(task_client, project["id"])
    for field, value, constraint in [
        ("task", str(uuid4()), "fk_task_command_task"),
        ("assignment", str(uuid4()), "task_command_state_shape"),
        ("contributor", str(uuid4()), "task_command_state_shape"),
        ("hash", None, "task_command_state_shape"),
        ("hash", "not-a-digest", "task_command_state_shape"),
        ("action", "task.claim", "task_command_state_shape"),
        ("action", "project.task.unknown", "task_command_action"),
    ]:
        params = dict(
            receipt_id=new_record_id(),
            actor=task["created_by"],
            task=task["id"],
            action="project.task.create",
            assignment=None,
            contributor=None,
            hash="sha256:" + "a" * 64,
        )
        params[field] = value
        async with db_session.get_session_factory()() as session:
            with pytest.raises(IntegrityError, match=constraint):
                await session.execute(
                    text("""insert into task_command_receipts
                  (id,actor_profile_id,action_id,idempotency_key,request_digest,task_id,status,
                   assignment_id,contributor_id,locked_context_hash,response,committed_at)
                  values(:receipt_id,:actor,:action,gen_random_uuid(),'sha256:'||repeat('a',64),
                         :task,'committed',:assignment,:contributor,:hash,'{}'::jsonb,now())"""),
                    params,
                )
                await session.commit()
            await session.rollback()


async def test_pending_create_requires_task_by_commit(task_client):
    project = await create_active_project(task_client)
    existing = await create_draft_task(task_client, project["id"])
    for insert_task in (False, True):
        task_id = str(new_record_id())
        async with db_session.get_session_factory()() as session:
            await session.execute(
                text("""insert into task_command_receipts
              (id,actor_profile_id,action_id,idempotency_key,request_digest,task_id,status)
              values(:receipt_id,:actor,'project.task.create',gen_random_uuid(),
                     'sha256:'||repeat('a',64),:task,'pending')"""),
                {
                    "receipt_id": new_record_id(),
                    "actor": existing["created_by"],
                    "task": task_id,
                },
            )
            if insert_task:
                await session.execute(
                    text("""insert into workstream_tasks
                    (id,project_id,title,description,status,created_by,skill_tags,source_type,task_size)
                    values(:task,:project,'Draft','Task body','draft',:actor,'[]','manual','small')"""),
                    {"task": task_id, "project": project["id"], "actor": existing["created_by"]},
                )
                await session.commit()
            else:
                with pytest.raises(IntegrityError, match="fk_task_command_task"):
                    await session.commit()
                await session.rollback()


async def test_missing_task_proof_detects_removed_custody_guard(task_client):
    project = await create_active_project(task_client)
    task = await create_draft_task(task_client, project["id"])

    async def assert_missing_task_rejected(session):
        with pytest.raises(IntegrityError, match="fk_task_command_task"):
            await session.execute(
                text("""insert into task_command_receipts
              (id,actor_profile_id,action_id,idempotency_key,request_digest,task_id,status)
              values(:receipt_id,:actor,'project.task.create',gen_random_uuid(),
                     'sha256:'||repeat('a',64),:task,'pending')"""),
                {
                    "receipt_id": new_record_id(),
                    "actor": task["created_by"],
                    "task": str(new_record_id()),
                },
            )
            await session.execute(text("set constraints all immediate"))

    async with db_session.get_session_factory()() as session:
        await assert_missing_task_rejected(session)
        await session.rollback()
    async with db_session.get_session_factory()() as session:
        try:
            await session.execute(
                text("alter table task_command_receipts drop constraint fk_task_command_task")
            )
            with pytest.raises(pytest.fail.Exception, match="DID NOT RAISE"):
                await assert_missing_task_rejected(session)
        finally:
            # Both the deliberately broken schema and orphan row are rolled back.
            await session.rollback()


async def insert_audit_copy(session, row, *, rejected):
    import json

    candidate = json.loads(json.dumps(row))
    candidate["id"] = str(new_record_id())
    transaction = await session.begin_nested()
    try:
        statement = text(
            "insert into audit_events select * from jsonb_populate_record(null::audit_events, cast(:row as jsonb))"
        )
        if rejected:
            with pytest.raises(IntegrityError, match="task management audit mismatch"):
                await session.execute(statement, {"row": json.dumps(candidate)})
        else:
            await session.execute(statement, {"row": json.dumps(candidate)})
    finally:
        await transaction.rollback()


@pytest.mark.parametrize("operation", ["create", "screen", "release"])
async def test_manager_audit_binds_exact_decision_and_task(task_client, monkeypatch, operation):
    import json
    from app.modules.audit.service import LifecycleAuditParticipant
    from tests.test_tasks import auth_headers, complete_task_payload

    project = await create_active_project(task_client)
    other = await create_draft_task(task_client, project["id"])
    target = await create_draft_task(task_client, project["id"]) if operation != "create" else None
    for task in (other, target):
        if task is None:
            continue
        if operation in {"screen", "release"}:
            # The other task completes the same action; target stops just before it.
            if task is other or operation == "release":
                response = await task_client.post(
                    f"/api/v1/tasks/{task['id']}/screen", headers=auth_headers()
                )
                assert response.status_code == 200, response.text
        if task is other and operation == "release":
            response = await task_client.post(
                f"/api/v1/tasks/{task['id']}/release",
                headers=auth_headers(),
                json={"reason": "Manager decision"},
            )
            assert response.status_code == 200, response.text
    event_type = {"create": "TaskCreated", "screen": "TaskScreened", "release": "TaskReleased"}[
        operation
    ]
    async with db_session.get_session_factory()() as session:
        wrong_decision = await session.scalar(
            text(
                "select event_payload->'references'->>'authorization_decision_id' from audit_events where entity_id=:task and event_type=:event"
            ),
            {"task": other["id"], "event": event_type},
        )
    original = LifecycleAuditParticipant.add_event
    observed = []

    async def inspect(participant, value):
        event = await original(participant, value)
        if event.event_type != event_type:
            return event
        session = participant._repository._session
        row = await session.scalar(
            text("select to_jsonb(a) from audit_events a where id=:id"), {"id": event.id}
        )
        await insert_audit_copy(session, row, rejected=False)
        mutations = ["decision", "context", "digest", "state", "extra"]
        mutations += ["source"] if operation == "create" else ["missing_lineage", "lineage"]
        for mutation in mutations:
            changed = json.loads(json.dumps(row))
            payload = changed["event_payload"]
            if mutation == "decision":
                payload["references"]["authorization_decision_id"] = wrong_decision
            elif mutation == "context":
                payload["manager_authority_facts"]["resource_id"] = other["id"]
            elif mutation == "digest":
                payload["authorization_resource_digest"] = "sha256:" + "a" * 64
            elif mutation == "state":
                changed["to_status"] = "in_progress"
            elif mutation == "source":
                payload["source_type"] = "csv_import"
            elif mutation == "missing_lineage":
                del payload["locked_review_policy_hash"]
            elif mutation == "lineage":
                payload["locked_review_policy_hash"] = "sha256:" + "a" * 64
            else:
                payload["private_material"] = "not permitted"
            await insert_audit_copy(session, changed, rejected=True)
        # Removing only the decision comparison must make the substitution proof fail.
        altered = json.loads(json.dumps(row))
        altered["event_payload"]["references"]["authorization_decision_id"] = wrong_decision
        function = await session.scalar(
            text("select pg_get_functiondef('guard_task_management_audit()'::regprocedure)")
        )
        comparison = "and decision.after_facts::jsonb=jsonb_build_object('allowed',true,'resource_context_digest',digest)"
        assert comparison in function
        transaction = await session.begin_nested()
        try:
            await session.execute(text(function.replace(comparison, "and true")))
            with pytest.raises(pytest.fail.Exception, match="DID NOT RAISE"):
                await insert_audit_copy(session, altered, rejected=True)
        finally:
            await transaction.rollback()
        observed.append(event.id)
        return event

    monkeypatch.setattr(LifecycleAuditParticipant, "add_event", inspect)
    path = (
        f"/api/v1/projects/{project['id']}/tasks"
        if operation == "create"
        else f"/api/v1/tasks/{target['id']}/{operation}"
    )
    response = await task_client.post(
        path,
        headers=auth_headers(),
        json=complete_task_payload() if operation == "create" else {"reason": "Manager decision"},
    )
    assert response.status_code == (201 if operation == "create" else 200), response.text
    assert len(observed) == 1
