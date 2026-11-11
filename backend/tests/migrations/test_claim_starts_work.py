"""Forward conversion of real predecessor claims without rewriting evidence."""

import asyncio
from datetime import UTC, datetime
from pathlib import Path
import runpy
from uuid import UUID

from alembic import command
from alembic.migration import MigrationContext
from alembic.operations import Operations
import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.adapters.artifacts import task_guide_documents_port
from app.adapters.audit import task_transition_audit
from app.adapters.tasks import task_service
from app.core.config import get_settings
from app.core.identifiers import new_record_id
from app.db import session as db_session
from app.modules.authorization.task_authorization import PreparedTaskAuthorization
from app.modules.tasks.api.authorization import TaskAuthorityOperation
from app.modules.tasks.authorized_commands import AuthorizedTaskCommands
from app.modules.tasks.models import AuditEvent, TaskAssignment, TaskCommandReceipt, WorkstreamTask
from app.modules.tasks.schemas import AssignmentResponse
from tests.authorization.task_authority.test_concurrency import actor_context
from tests.conftest import _drop_test_database_schema
from tests.migration_fixtures import _config
from tests.migration_revision_fixtures import (
    _restore_historical_revision_rows, assert_historical_revision_guards,
    add_retained_guide_read_projection, drop_retained_guide_read_projection,
    add_historical_revision_read_projection, enter_predecessor_owner_shape,
    leave_predecessor_owner_shape,
)
from tests.project_create_fixtures import grant_fixture_admin_role
from tests.test_alembic import _execute
from tests.test_tasks import (
    task_client as current_task_client,
    task_database_env as task_database_env,
    actor_id,
    admit_and_grant_project_submitter,
    create_ready_task,
)

pytestmark = pytest.mark.postgres_schema_contract
_PATH = Path(__file__).parents[2] / "alembic/versions/0065_claim_starts_work.py"


def _upgrade(connection):
    with Operations.context(MigrationContext.configure(connection)):
        runpy.run_path(str(_PATH))["upgrade"]()


@pytest.fixture
async def predecessor_client(task_database_env, migration_lock):
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
        # Current TASK owners read retained guide custody through current ORM
        # columns. These null-only projections are removed before the upgrade.
        async with db_session.get_engine().begin() as connection:
            await add_retained_guide_read_projection(connection)
            await connection.execute(text(
                "ALTER TABLE actor_identity_links ADD COLUMN email_observed_issued_at bigint"
            ))
    async for client in current_task_client.__wrapped__(task_database_env):
        project_id = seed["request"]["project_id"]
        await assert_historical_revision_guards(
            db_session.get_session_factory(), "0064_checker_trial_evidence",
        )
        manager_id = await actor_id("project-manager-subject")
        async with db_session.get_session_factory()() as session, session.begin():
            await grant_fixture_admin_role(
                session, manager_id, project_id=project_id,
            )
        yield client, project_id


async def _claim(session, task_id, actor_id, *, started=False):
    """Write the predecessor owner's assignment, transition and committed receipt.

    Current public claim intentionally cannot create the predecessor state. These
    are its original stored facts, with every live predecessor guard enabled.
    """
    context = await actor_context(actor_id)
    owner = AuthorizedTaskCommands(
        session, authorization=PreparedTaskAuthorization(session, context),
        audit=task_transition_audit(session), actor_profile_id=context.actor_profile_id,
        contexts=task_service(session, settings=get_settings()),
        guide_documents=task_guide_documents_port(session, get_settings()),
    )
    receipt, _, _ = await owner._replay.reserve(
        UUID(actor_id), TaskAuthorityOperation.CLAIM, new_record_id(), UUID(task_id), "historical claim",
    )
    task, _, decision = await owner._locked_task(
        UUID(task_id), TaskAuthorityOperation.CLAIM, "historical claim",
        idempotency_key=receipt.idempotency_key, receipt=receipt,
    )
    facts = owner._facts(task, None, TaskAuthorityOperation.CLAIM, "historical claim", receipt.idempotency_key)
    captured_task = owner._contexts.task_response_for_authority(task, can_manage=False).model_dump(mode="json")
    captured_task["status"], captured_task["assigned_to"] = "claimed", actor_id
    now = datetime.now(UTC)
    assignment = TaskAssignment(
        id=str(new_record_id()), task_id=task.id, project_id=task.project_id,
        contributor_id=actor_id, assigned_by=actor_id, assigned_at=now, accepted_at=now,
        submitter_contribution_policy_version_id=task.locked_contribution_policy_version_id,
        status="active",
    )
    session.add(assignment)
    await session.flush()
    task.assigned_to, task.status = actor_id, "claimed"
    await session.flush()
    refs = {"project_id": task.project_id, "task_id": task.id,
            "assignment_id": assignment.id, "authorization_decision_id": str(decision.decision_id)}
    session.add(AuditEvent(
        id=str(new_record_id()), entity_type="task", entity_id=task.id,
        event_type="TaskClaimed", from_status="ready", to_status="claimed", actor_id=actor_id,
        external_subject="workstream:lifecycle-participant", external_issuer="workstream:internal",
        actor_roles=[], claim_snapshot={}, auth_source="local_lifecycle", is_dev_auth=False,
        reason="historical claim", event_payload={"references": refs},
    ))
    receipt.status, receipt.assignment_id, receipt.contributor_id = "committed", assignment.id, actor_id
    receipt.locked_context_hash, receipt.committed_at = facts.locked_context_hash, now
    receipt.response = {"task": captured_task, "assignment": AssignmentResponse.model_validate(assignment).model_dump(mode="json")}
    await session.flush()
    if started:
        task.status = "in_progress"
        await session.flush()
        assignment.started_at = now
        await session.flush()
    return task, assignment


async def _setup(predecessor, monkeypatch):
    client, project_id = predecessor
    tasks = [await create_ready_task(client, project_id) for _ in range(3)]
    grant = await admit_and_grant_project_submitter(client, monkeypatch, project_id, "historical-claimant")
    return tasks, grant["actor_profile_id"]


async def _snapshot(session):
    return {
        table: list(await session.scalars(text(
            f"SELECT jsonb_build_array(to_jsonb(row),xmin::text) FROM public.{table} row ORDER BY id"
        )))
        for table in ("workstream_tasks", "task_assignments", "audit_events", "task_command_receipts")
    }


async def test_upgrade_starts_only_retained_claim_and_preserves_evidence(predecessor_client, monkeypatch):
    tasks, actor = await _setup(predecessor_client, monkeypatch)
    async with db_session.get_session_factory()() as session:
        task, prior = await _claim(session, tasks[0]["id"], actor, started=True)
        prior.status, prior.released_at = "released", datetime.now(UTC)
        task.status, task.assigned_to = "ready", None
        await session.flush()
        # Prior released work has legitimate start history on the same task.
        session.add(AuditEvent(
            id=str(new_record_id()), entity_type="task", entity_id=task.id,
            event_type="TaskStarted", from_status="claimed", to_status="in_progress", actor_id=actor,
            external_subject="workstream:lifecycle-participant", external_issuer="workstream:internal",
            actor_roles=[], claim_snapshot={}, auth_source="local_lifecycle", is_dev_auth=False,
            reason="historical start", event_payload={"references": {"assignment_id": prior.id}},
        ))
        session.add(TaskCommandReceipt(
            id=new_record_id(), actor_profile_id=actor, action_id="task.start", idempotency_key=new_record_id(),
            request_digest="sha256:" + "a" * 64, task_id=task.id, status="committed",
            assignment_id=prior.id, contributor_id=actor, locked_context_hash="sha256:" + "a" * 64,
            response={"status": "in_progress"}, committed_at=datetime.now(UTC),
        ))
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
    async with db_session.get_engine().begin() as connection:
        await drop_retained_guide_read_projection(connection)
        await connection.execute(text(
            "ALTER TABLE actor_identity_links DROP COLUMN email_observed_issued_at"
        ))
    await db_session.dispose_engine()
    await asyncio.to_thread(command.upgrade, _config(), "head")
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
        assignment = await session.get(TaskAssignment, assignment_id)
        assert assignment.started_at == assignment.assigned_at
        assert (await session.get(WorkstreamTask, tasks[0]["id"])).status == "in_progress"
        with pytest.raises(IntegrityError, match="assignment start requires the started task"):
            async with session.begin_nested():
                await session.execute(text("UPDATE task_assignments SET started_at=started_at+interval '1 second' WHERE id=:id"), {"id": assignment_id})
        with pytest.raises(IntegrityError, match="ck_workstream_tasks_status"):
            async with session.begin_nested():
                await session.execute(text("UPDATE workstream_tasks SET status='claimed' WHERE id=:id"), {"id": tasks[0]["id"]})


async def test_invalid_current_claim_refuses_entire_upgrade(predecessor_client, monkeypatch):
    tasks, actor = await _setup(predecessor_client, monkeypatch)
    async with db_session.get_session_factory()() as session:
        # A valid claim first proves failure cannot partially convert other rows.
        await _claim(session, tasks[0]["id"], actor)
        task, assignment = await _claim(session, tasks[1]["id"], actor)
        task_id, assignment_id, other_actor = task.id, assignment.id, task.created_by
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
                    session.add(AuditEvent(
                        id=str(new_record_id()), entity_type="task", entity_id=task_id,
                        event_type="TaskStarted", from_status="claimed", to_status="in_progress", actor_id=actor,
                        external_subject="workstream:lifecycle-participant", external_issuer="workstream:internal",
                        actor_roles=[], claim_snapshot={}, auth_source="local_lifecycle", is_dev_auth=False,
                        reason="contradictory start", event_payload={"references": {"assignment_id": assignment_id}},
                    ))
                elif case == "start_receipt":
                    session.add(TaskCommandReceipt(
                        id=new_record_id(), actor_profile_id=actor, action_id="task.start", idempotency_key=new_record_id(),
                        request_digest="sha256:" + "a" * 64, task_id=task_id, status="committed",
                        assignment_id=assignment_id, contributor_id=actor, locked_context_hash="sha256:" + "a" * 64,
                        response={"status": "in_progress"}, committed_at=datetime.now(UTC),
                    ))
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
