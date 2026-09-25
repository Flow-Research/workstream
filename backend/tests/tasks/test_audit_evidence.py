"""Scoped immutable audit evidence through real PostgreSQL and existing writers."""

import asyncio
from dataclasses import FrozenInstanceError, asdict, replace
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch
from uuid import UUID
from app.core.identifiers import new_record_id

import pytest
from sqlalchemy import event as sql_events, select

from app.db import session as db_session
from app.modules.audit.repository import AuditRepository, LIFECYCLE_AUTH_SOURCE
from app.modules.audit.schemas import (
    LifecycleAuditEntityType, LifecycleAuditEventInput, LifecycleAuditEventType,
    LifecycleAuditReason, LifecycleAuditReferenceKind,
)
from app.modules.audit.service import LifecycleAuditParticipant
from app.modules.tasks.api import (
    AuditTaskEvidence, AuditTaskEvidencePage, AuditTaskEvidenceRequest,
    TaskEvidenceCursor, TaskEvidenceInvalid,
)
from app.modules.tasks.models import AuditEvent, WorkstreamTask
from app.modules.tasks.repository import TaskRepository
from tests.test_tasks import (
    task_database_env as task_database_env, task_client as task_client,
    create_active_project, create_draft_task, create_ready_task,
)

NOW = datetime(2030, 1, 1, tzinfo=UTC)
FIELDS = {"event_id", "event_type", "from_status", "to_status", "actor_id", "created_at",
          "assignment_id", "authorization_decision_id"}


def request(project, task, **kwargs):
    return AuditTaskEvidenceRequest(UUID(project["id"]), UUID(task["id"]), **kwargs)


async def store_event(session, task_id, *, when=NOW, event_type="fixture_event", entity_type="task", payload=None, typed_source=False):
    value = AuditEvent(
        id=str(new_record_id()), entity_type=entity_type, entity_id=task_id, event_type=event_type,
        actor_id="recorded-actor", external_subject="private-subject", external_issuer="private-issuer",
        actor_roles=["private-role"], claim_snapshot={"secret": "private-claim"},
        auth_source=LIFECYCLE_AUTH_SOURCE if typed_source else "flow_jwt", reason="private-reason", event_payload=payload or {"private": "private-payload"},
        created_at=when,
    )
    if typed_source:
        # Faulty-writer counterexample: bypass Python validation, keep every DB guard.
        session.add(value)
        await session.flush()
        return value
    return await AuditRepository(session).add_audit_event(value)


async def read_once(session, value):
    statements = []
    def capture(_conn, _cursor, statement, _parameters, _context, _many):
        statements.append(statement)
    engine = session.bind.sync_engine
    sql_events.listen(engine, "before_cursor_execute", capture)
    try:
        with patch.object(session, "execute", wraps=session.execute) as execute:
            result = await TaskRepository(session).read_audit_task_evidence(value)
        execute.assert_awaited_once()
        assert len(statements) == 1
        return result
    finally:
        sql_events.remove(engine, "before_cursor_execute", capture)


def test_task_evidence_contracts():
    project, task, event = new_record_id(), new_record_id(), new_record_id()
    cursor = TaskEvidenceCursor(project, task, NOW, event)
    req = AuditTaskEvidenceRequest(project, task, after=cursor)
    item = AuditTaskEvidence(event, "event", None, None, "actor", NOW, None, None)
    page = AuditTaskEvidencePage(project, task, (item,), cursor)
    assert set(asdict(item)) == FIELDS
    for value, changes in (
        (cursor, ({"project_id": "bad"}, {"task_id": "bad"}, {"event_id": "bad"}, {"created_at": datetime.now()})),
        (req, ({"project_id": "bad"}, {"task_id": "bad"}, *({"limit": v} for v in [0, 101, True, 1.5, "1"]),
               {"after": {}}, {"after": replace(cursor, project_id=new_record_id())}, {"after": replace(cursor, task_id=new_record_id())})),
        (item, (*({field: []} for field in FIELDS), {"created_at": datetime.now()}, {"assignment_id": new_record_id()})),
        (page, ({"project_id": "bad"}, {"task_id": "bad"}, {"items": []}, {"items": ({},)}, {"items": (item,) * 101},
                {"items": ()}, {"next_cursor": {}}, {"next_cursor": replace(cursor, event_id=new_record_id())})),
    ):
        for change in changes:
            with pytest.raises(ValueError):
                replace(value, **change)
        with pytest.raises(FrozenInstanceError):
            setattr(value, next(iter(asdict(value))), "mutated")
    assert replace(item, assignment_id=new_record_id(), authorization_decision_id=new_record_id()).assignment_id
    assert AuditTaskEvidencePage(project, task, (), None).items == ()


async def test_task_evidence_rejects_before_sql():
    session = MagicMock()
    for value in ({}, None):
        with pytest.raises(ValueError, match="request is invalid"):
            await TaskRepository(session).read_audit_task_evidence(value)
    session.execute.assert_not_called()


async def test_task_evidence_project_scope(task_client):
    project = await create_active_project(task_client)
    foreign = await create_active_project(task_client, slug="foreign-evidence")
    outsider = await create_draft_task(task_client, foreign["id"])
    states = {"draft", "screening", "ready", "claimed", "in_progress", "submitted", "evaluation_pending", "review_pending", "needs_revision"}
    tasks = {status: await (create_draft_task if status == "draft" else create_ready_task)(task_client, project["id"]) for status in states}
    factory = db_session.get_session_factory()
    async with factory() as session, session.begin():
        for status, task in tasks.items():
            row = await session.get(WorkstreamTask, task["id"])
            if status != "draft":
                assert row.locked_contribution_policy_version_id is not None
            row.status = status
    async with factory() as session:
        for status, task in tasks.items():
            assert (await session.get(WorkstreamTask, task["id"])).status == status
            page = await read_once(session, request(project, task))
            assert page.project_id == UUID(project["id"]) and page.task_id == UUID(task["id"])
            assert page.items and page.items[0].event_type == "TaskCreated"
        for value in (request(project, outsider), AuditTaskEvidenceRequest(new_record_id(), UUID(tasks["draft"]["id"])),
                      AuditTaskEvidenceRequest(UUID(project["id"]), new_record_id())):
            assert await read_once(session, value) is None


async def test_task_evidence_project_move(task_client):
    project = await create_active_project(task_client)
    other = await create_active_project(task_client, slug="moved-evidence")
    task = await create_draft_task(task_client, project["id"])
    factory = db_session.get_session_factory()
    async with factory() as reader:
        assert await read_once(reader, request(project, task))
        async with factory() as writer, writer.begin():
            row = await writer.get(WorkstreamTask, task["id"])
            assert row.status == "draft"
            row.project_id = other["id"]
        assert await read_once(reader, request(project, task)) is None
        # A moved draft cannot reattribute its immutable creation decision.
        with pytest.raises(TaskEvidenceInvalid):
            await read_once(reader, request(other, task))


async def test_task_evidence_pagination(task_client):
    project = await create_active_project(task_client)
    other = await create_active_project(task_client, slug="pagination-evidence")
    task, sibling = [await create_draft_task(task_client, project["id"]) for _ in range(2)]
    foreign = await create_draft_task(task_client, other["id"])
    factory = db_session.get_session_factory()
    async with factory() as session, session.begin():
        expected = []
        for index in range(3):
            for decoy in (sibling, foreign):
                await store_event(session, decoy["id"], when=NOW - timedelta(seconds=1))
            await store_event(session, task["id"], entity_type="review", when=NOW - timedelta(seconds=1))
            expected.append(UUID((await store_event(session, task["id"])).id))
    cursor = TaskEvidenceCursor(UUID(project["id"]), UUID(task["id"]), NOW - timedelta(seconds=2), new_record_id())
    value = request(project, task, limit=1, after=cursor)
    async with factory() as session:
        assert len(list(await session.scalars(select(AuditEvent.id).where(AuditEvent.entity_id == task["id"])))) == 7
        for index, event_id in enumerate(sorted(expected)):
            page = await read_once(session, value)
            assert [item.event_id for item in page.items] == [event_id]
            if index < 2:
                assert page.next_cursor == TaskEvidenceCursor(value.project_id, value.task_id, NOW, event_id)
                value = replace(value, after=page.next_cursor)
            else:
                assert page.next_cursor is None
        exhausted = await read_once(session, replace(value, after=TaskEvidenceCursor(value.project_id, value.task_id, NOW, max(expected))))
        assert exhausted.items == () and exhausted.next_cursor is None
        empty_task = await session.get(WorkstreamTask, sibling["id"])
        # New task fixture has no audit writer call; no retained evidence is deleted.
        empty = WorkstreamTask(id=str(new_record_id()), project_id=project["id"], title="empty", description="empty",
                              source_type=empty_task.source_type, status="draft", created_by=empty_task.created_by)
        session.add(empty)
        await session.flush()
        assert (await read_once(session, AuditTaskEvidenceRequest(value.project_id, UUID(empty.id)))).items == ()


async def test_task_evidence_transition_references(task_client):
    project = await create_active_project(task_client)
    task = await create_draft_task(task_client, project["id"])
    value = request(project, task, after=TaskEvidenceCursor(UUID(project["id"]), UUID(task["id"]), NOW - timedelta(seconds=1), new_record_id()))
    refs = {"project_id": value.project_id, "task_id": value.task_id, "assignment_id": new_record_id(), "authorization_decision_id": new_record_id()}
    factory = db_session.get_session_factory()
    for event_type in ("TaskClaimed", "TaskStarted", "TaskStartOverridden"):
        async with factory() as session:
            event = await LifecycleAuditParticipant(session).add_event(LifecycleAuditEventInput(
                event_id=new_record_id(), entity_type=LifecycleAuditEntityType.TASK, entity_id=value.task_id, event_type=LifecycleAuditEventType(event_type),
                actor_id=new_record_id(), from_status="ready" if event_type == "TaskClaimed" else "claimed",
                to_status="claimed" if event_type == "TaskClaimed" else "in_progress",
                task_reason="reasoned override" if event_type == "TaskStartOverridden" else None,
                reason=LifecycleAuditReason.STATE_CHANGED,
                references={LifecycleAuditReferenceKind(key): val for key, val in refs.items()},
            ))
            page = await read_once(session, replace(value, after=None))
            item = next(item for item in page.items if item.event_id == UUID(event.id))
            assert (item.assignment_id, item.authorization_decision_id) == (refs["assignment_id"], refs["authorization_decision_id"])
            await session.rollback()
        for field in refs:
            for bad in (None, "private-malformed", *((str(new_record_id()),) if field in {"project_id", "task_id"} else ())):
                broken = {key: str(val) for key, val in refs.items()}
                if bad is None:
                    broken.pop(field)
                else:
                    broken[field] = bad
                async with factory() as session:
                    stored = await store_event(session, task["id"], event_type=event_type, payload={"references": broken}, typed_source=True)
                    assert await session.scalar(select(AuditEvent.id).where(AuditEvent.id == stored.id)) == stored.id
                    with pytest.raises(TaskEvidenceInvalid, match="^task audit evidence is invalid$"):
                        await read_once(session, value)
                    await session.rollback()


async def test_task_evidence_source_provenance(task_client):
    project = await create_active_project(task_client)
    task = await create_draft_task(task_client, project["id"])
    value = request(project, task)
    refs = {"project_id": project["id"], "task_id": task["id"],
            "assignment_id": str(new_record_id()), "authorization_decision_id": str(new_record_id())}
    factory = db_session.get_session_factory()
    for event_type in ("TaskClaimed", "TaskStarted", "TaskStartOverridden"):
        async with factory() as session:
            stored = await store_event(session, task["id"], event_type=event_type, payload={"references": refs})
            assert await session.scalar(select(AuditEvent.auth_source).where(AuditEvent.id == stored.id)) == "flow_jwt"
            with pytest.raises(TaskEvidenceInvalid, match="^task audit evidence is invalid$"):
                await read_once(session, value)
            await session.rollback()
    for typed_source in (False, True):
        async with factory() as session:
            stored = await store_event(session, task["id"], payload={"references": refs}, typed_source=typed_source)
            rows = await AuditRepository(session).read_task_evidence_rows(value.project_id, value.task_id, 50, None, None)
            row = next(row for row in rows if row.event_id == stored.id)
            assert (row.reference_project_id, row.reference_task_id, row.assignment_id, row.authorization_decision_id) == (None,) * 4
            item = next(item for item in (await read_once(session, value)).items if item.event_id == UUID(stored.id))
            assert item.assignment_id is None and item.authorization_decision_id is None
            await session.rollback()


async def test_task_evidence_sql_privacy(task_client):
    project = await create_active_project(task_client)
    task = await create_draft_task(task_client, project["id"])
    async with db_session.get_session_factory()() as session:
        stored = await store_event(session, task["id"])
        assert stored.claim_snapshot and stored.reason and stored.event_payload
        with patch.object(session, "execute", wraps=session.execute) as execute:
            page = await TaskRepository(session).read_audit_task_evidence(request(project, task))
        execute.assert_awaited_once()
        statement = execute.await_args.args[0]
        assert len(statement.selected_columns) == 11
        assert set(statement.selected_columns.keys()) == {
            "scoped_task_id", "event_id", "event_type", "from_status", "to_status", "actor_id", "created_at",
            "reference_project_id", "reference_task_id", "assignment_id", "authorization_decision_id",
        }
        assert "LEFT OUTER JOIN" in str(statement) and statement._for_update_arg is None
        assert all(set(asdict(item)) == FIELDS for item in page.items)
        assert "private-" not in str(asdict(page))
        assert stored not in session.dirty


async def test_task_evidence_caller_transaction(task_client):
    project = await create_active_project(task_client)
    task = await create_draft_task(task_client, project["id"])
    factory = db_session.get_session_factory()
    async with factory() as session:
        row = await session.get(WorkstreamTask, task["id"])
        original = row.title
        row.title = "uncommitted"
        await session.flush()
        event = await store_event(session, task["id"])
        event_id = UUID(event.id)
        invalid = WorkstreamTask(id=str(new_record_id()))
        session.add(invalid)
        page = await read_once(session, request(project, task))
        assert event_id in {item.event_id for item in page.items}
        assert invalid in session.new and session.in_transaction()
        await session.rollback()
    async with factory() as observer:
        assert (await observer.get(WorkstreamTask, task["id"])).title == original
        assert await observer.get(AuditEvent, str(event_id)) is None


async def test_task_evidence_does_not_lock(task_client):
    project = await create_active_project(task_client)
    task = await create_draft_task(task_client, project["id"])
    factory = db_session.get_session_factory()
    async with factory() as writer, writer.begin():
        row = await writer.scalar(select(WorkstreamTask).where(WorkstreamTask.id == task["id"]).with_for_update())
        row.title = "writer-uncommitted"
        await writer.flush()
        async with factory() as reader:
            page = await asyncio.wait_for(read_once(reader, request(project, task)), timeout=5)
            assert page.items and reader.in_transaction()
