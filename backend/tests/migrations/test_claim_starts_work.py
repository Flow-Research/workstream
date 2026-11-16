"""Exact predecessor claim conversion without current runtime compatibility."""

import asyncio
import json
from pathlib import Path
import runpy
from types import SimpleNamespace

from alembic import command
from alembic.migration import MigrationContext
from alembic.operations import Operations
import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.core.identifiers import new_record_id
from app.db import session as db_session
from tests.conftest import _drop_test_database_schema
from tests.migration_fixtures import _config
from tests.migration_revision_fixtures import (
    _restore_historical_revision_rows, assert_historical_revision_guards,
    add_historical_revision_read_projection, enter_predecessor_owner_shape,
    leave_predecessor_owner_shape,
)
from tests.test_alembic import _execute
from tests.test_tasks import task_database_env as task_database_env

pytestmark = pytest.mark.postgres_schema_contract
_PATH = Path(__file__).parents[2] / "alembic/versions/0065_claim_starts_work.py"


def _upgrade(connection):
    with Operations.context(MigrationContext.configure(connection)):
        runpy.run_path(str(_PATH))["upgrade"]()


@pytest.fixture
async def predecessor_rows(task_database_env, migration_lock):
    """Restore archived data; expose no current reader or application writer."""
    await db_session.dispose_engine()
    with migration_lock():
        await _drop_test_database_schema(task_database_env)
        await asyncio.to_thread(command.upgrade, _config(), "0047_revision_recovery")
        shape = pytest.MonkeyPatch()
        await enter_predecessor_owner_shape(_execute, task_database_env, shape)
        try:
            seed = await _restore_historical_revision_rows(
                task_database_env, "0047_revision_source_default",
            )
            async with db_session.get_engine().begin() as connection:
                await add_historical_revision_read_projection(connection)
        finally:
            shape.undo()
        await leave_predecessor_owner_shape(_execute, task_database_env)
        await db_session.dispose_engine()
        await asyncio.to_thread(command.upgrade, _config(), "0064_checker_trial_evidence")
    await assert_historical_revision_guards(
        db_session.get_session_factory(), "0064_checker_trial_evidence",
    )
    yield seed


async def _audit(session, task, assignment, actor, *, started=False):
    event, before, after = (("TaskStarted", "claimed", "in_progress") if started
                            else ("TaskClaimed", "ready", "claimed"))
    await session.execute(text("""
        INSERT INTO public.audit_events
          (id,event_domain,entity_type,entity_id,event_type,from_status,to_status,actor_id,
           external_subject,external_issuer,actor_roles,claim_snapshot,auth_source,
           is_dev_auth,reason,event_payload)
        VALUES (:id,'legacy_lifecycle','task',:task,:event,:before,:after,:actor,
          'workstream:lifecycle-participant','workstream:internal','[]'::json,
          '{}'::json,'local_lifecycle',false,'retained predecessor evidence',CAST(:payload AS json))
    """), dict(id=new_record_id(), task=task, event=event, before=before, after=after,
               actor=actor, payload=json.dumps({"references": {"task_id": str(task),
               "assignment_id": str(assignment)}})))


async def _receipt(session, task, assignment, actor, *, started=False):
    response = await session.scalar(text("""
        SELECT jsonb_build_object('task',to_jsonb(t),'assignment',to_jsonb(a))
        FROM public.workstream_tasks t JOIN public.task_assignments a ON a.task_id=t.id
        WHERE t.id=:task AND a.id=:assignment
    """), {"task": task, "assignment": assignment})
    assert response["task"]["assigned_to"] == str(actor)
    digest = await session.scalar(text(
        "SELECT public.revision_task_context_digest(t) FROM public.workstream_tasks t WHERE id=:id"
    ), {"id": task})
    await session.execute(text("""
        INSERT INTO public.task_command_receipts
          (id,actor_profile_id,action_id,idempotency_key,request_digest,task_id,status,
           assignment_id,contributor_id,locked_context_hash,response,committed_at)
        VALUES (:id,:actor,:action,:key,:digest,:task,'committed',:assignment,:actor,
                :digest,CAST(:response AS jsonb),clock_timestamp())
    """), dict(id=new_record_id(), actor=actor, action="task.start" if started else "task.claim",
               key=new_record_id(), digest=digest, task=task, assignment=assignment,
               response=json.dumps(response)))


async def _claim(session, task_id, actor_id, *, started=False):
    """Prepare stored predecessor facts under its guards, without claiming AUTH proof."""
    assignment_id = str(new_record_id())
    await session.execute(text("""
        INSERT INTO public.task_assignments
          (id,task_id,project_id,contributor_id,assigned_by,assigned_at,accepted_at,
           submitter_contribution_policy_version_id,status)
        SELECT :id,t.id,t.project_id,:actor,:actor,clock_timestamp(),clock_timestamp(),
               t.locked_contribution_policy_version_id,'active'
        FROM public.workstream_tasks t WHERE t.id=:task
    """), {"id": assignment_id, "actor": actor_id, "task": task_id})
    await session.execute(text("UPDATE public.workstream_tasks SET status='claimed',assigned_to=:actor WHERE id=:task"),
                          {"actor": actor_id, "task": task_id})
    await _audit(session, task_id, assignment_id, actor_id)
    await _receipt(session, task_id, assignment_id, actor_id)
    if started:
        await session.execute(text("UPDATE public.workstream_tasks SET status='in_progress' WHERE id=:id"), {"id": task_id})
        await session.execute(text("UPDATE public.task_assignments SET started_at=assigned_at WHERE id=:id"), {"id": assignment_id})
    return SimpleNamespace(id=task_id), SimpleNamespace(id=assignment_id)


async def _setup(seed):
    actor = seed["actor_context"]["actor_profile_id"]
    source = seed["request"]["task_id"]
    tasks = []
    async with db_session.get_session_factory()() as session, session.begin():
        assert await session.scalar(text("SELECT actor_kind FROM public.actor_profiles WHERE id=:id"), {"id": actor}) == "human"
        clone = text("""
            INSERT INTO public.workstream_tasks
            SELECT (jsonb_populate_record(NULL::public.workstream_tasks,
                    to_jsonb(t)||CAST(:changes AS jsonb))).*
            FROM public.workstream_tasks t WHERE t.id=:source RETURNING id
        """)
        with pytest.raises(IntegrityError, match="task contribution stamp requires initial screening"):
            async with session.begin_nested():
                await session.execute(clone, {"source": source, "changes": json.dumps({
                    "id": str(new_record_id()), "status": "ready", "assigned_to": None,
                    "external_task_id": None, "import_batch_id": None,
                })})
        for _ in range(3):
            task_id = str(new_record_id())
            stored = await session.scalar(clone, {"source": source, "changes": json.dumps({
                "id": task_id, "status": "draft", "assigned_to": None,
                "locked_contribution_policy_version_id": None,
                "source_ref": task_id, "external_task_id": None, "import_batch_id": None,
            })})
            assert str(stored) == task_id
            await session.execute(text("""
                UPDATE public.workstream_tasks SET status='screening',
                  locked_contribution_policy_version_id=(SELECT locked_contribution_policy_version_id
                    FROM public.workstream_tasks WHERE id=:source) WHERE id=:task
            """), {"source": source, "task": task_id})
            await session.execute(text("UPDATE public.workstream_tasks SET status='ready' WHERE id=:id"), {"id": task_id})
            tasks.append({"id": task_id})
        await session.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
    return tasks, actor


async def _snapshot(session):
    return {
        table: list(await session.scalars(text(
            f"SELECT jsonb_build_array(to_jsonb(row),xmin::text) FROM public.{table} row ORDER BY id"
        )))
        for table in ("workstream_tasks", "task_assignments", "audit_events", "task_command_receipts")
    }


async def test_upgrade_starts_only_retained_claim_and_preserves_evidence(predecessor_rows):
    """Upgrade a retained claim while preserving unrelated assignments, receipts and audit rows."""
    tasks, actor = await _setup(predecessor_rows)
    async with db_session.get_session_factory()() as session:
        task, prior = await _claim(session, tasks[0]["id"], actor, started=True)
        await _audit(session, task.id, prior.id, actor, started=True)
        await _receipt(session, task.id, prior.id, actor, started=True)
        await session.execute(text("UPDATE task_assignments SET status='released',released_at=clock_timestamp() WHERE id=:id"), {"id": prior.id})
        await session.execute(text("UPDATE workstream_tasks SET status='ready',assigned_to=NULL WHERE id=:id"), {"id": task.id})
        _, assignment = await _claim(session, task.id, actor)
        await _claim(session, tasks[1]["id"], actor, started=True)
        await session.flush()
        # The unchanged predecessor guard rejects a stamp before task start.
        with pytest.raises(IntegrityError, match="assignment start requires the started task"):
            async with session.begin_nested():
                await session.execute(text("UPDATE task_assignments SET started_at=assigned_at WHERE id=:id"), {"id": assignment.id})
        await session.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
        before = await _snapshot(session)
        assignment_id = assignment.id
        await session.commit()
    await db_session.dispose_engine()
    await asyncio.to_thread(command.upgrade, _config(), "0065_claim_starts_work")
    async with db_session.get_session_factory()() as session:
        after = await _snapshot(session)
        for table in ("audit_events", "task_command_receipts"):
            assert after[table] == before[table]
        for table, changed_id, fields in (
            ("workstream_tasks", tasks[0]["id"], {"status", "updated_at"}),
            ("task_assignments", assignment_id, {"started_at", "updated_at"}),
        ):
            for old, new in zip(before[table], after[table], strict=True):
                if old[0]["id"] != changed_id:
                    assert new == old
                else:
                    assert {k: v for k, v in new[0].items() if k not in fields} == {
                        k: v for k, v in old[0].items() if k not in fields}
        assert await session.scalar(text("SELECT version_num FROM alembic_version")) == "0065_claim_starts_work"
        stamps = (await session.execute(text("SELECT started_at,assigned_at FROM task_assignments WHERE id=:id"), {"id": assignment_id})).one()
        assert stamps.started_at == stamps.assigned_at
        assert await session.scalar(text("SELECT status FROM workstream_tasks WHERE id=:id"), {"id": tasks[0]["id"]}) == "in_progress"
        with pytest.raises(IntegrityError, match="assignment start requires the started task"):
            async with session.begin_nested():
                await session.execute(text("UPDATE task_assignments SET started_at=started_at+interval '1 second' WHERE id=:id"), {"id": assignment_id})
        with pytest.raises(IntegrityError, match="ck_workstream_tasks_status"):
            async with session.begin_nested():
                await session.execute(text("UPDATE workstream_tasks SET status='claimed' WHERE id=:id"), {"id": tasks[0]["id"]})


async def test_invalid_current_claim_refuses_entire_upgrade(predecessor_rows):
    tasks, actor = await _setup(predecessor_rows)
    async with db_session.get_session_factory()() as session:
        # A valid claim first proves failure cannot partially convert other rows.
        await _claim(session, tasks[0]["id"], actor)
        task, assignment = await _claim(session, tasks[1]["id"], actor)
        task_id, assignment_id = task.id, assignment.id
        other_actor = await session.scalar(text("SELECT id FROM actor_profiles WHERE actor_kind='human' AND id<>:actor ORDER BY id LIMIT 1"), {"actor": actor})
        assert other_actor is not None and str(other_actor) != actor
        await session.flush()
        for case in ("missing_assignment", "unaccepted", "missing_assignee", "wrong_assignee", "released", "started", "start_event", "start_receipt"):
            mutation = await session.begin_nested()
            try:
                if case in {"missing_assignment", "unaccepted", "released"}:
                    change = {"missing_assignment": "status='released'", "unaccepted": "accepted_at=NULL",
                              "released": "released_at=clock_timestamp()"}[case]
                    await session.execute(text(f"UPDATE task_assignments SET {change} WHERE id=:id"), {"id": assignment_id})
                elif case == "missing_assignee":
                    await session.execute(text("UPDATE workstream_tasks SET assigned_to=NULL WHERE id=:id"), {"id": task_id})
                elif case == "wrong_assignee":
                    await session.execute(text("UPDATE workstream_tasks SET assigned_to=:actor WHERE id=:id"), {"id": task_id, "actor": other_actor})
                elif case == "started":
                    await session.execute(text("UPDATE workstream_tasks SET status='in_progress' WHERE id=:id"), {"id": task_id})
                    await session.execute(text("UPDATE task_assignments SET started_at=assigned_at WHERE id=:id"), {"id": assignment_id})
                    await session.execute(text("UPDATE workstream_tasks SET status='claimed' WHERE id=:id"), {"id": task_id})
                elif case == "start_event":
                    await _audit(session, task_id, assignment_id, actor, started=True)
                elif case == "start_receipt":
                    await _receipt(session, task_id, assignment_id, actor, started=True)
                await session.flush()
                await session.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
                before = await _snapshot(session)
                constraint = await session.scalar(text("SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE conname='ck_workstream_tasks_status'"))
                with pytest.raises(IntegrityError, match="ambiguous current assignment lineage"):
                    async with session.begin_nested():
                        connection = await session.connection()
                        await connection.run_sync(_upgrade)
                assert await _snapshot(session) == before, case
                assert await session.scalar(text("SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE conname='ck_workstream_tasks_status'")) == constraint
                assert await session.scalar(text("SELECT version_num FROM alembic_version")) == "0064_checker_trial_evidence"
            finally:
                await mutation.rollback()


def test_downgrade_refused():
    with pytest.raises(RuntimeError, match="cannot be downgraded"):
        runpy.run_path(str(_PATH))["downgrade"]()
