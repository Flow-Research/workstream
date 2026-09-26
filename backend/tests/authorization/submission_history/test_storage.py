"""Retained evidence constraints survive removal of the alternate checker writer."""

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError

from app.core.identifiers import new_record_id
from app.db import session as db_session
from app.modules.tasks.models import Submission
from app.modules.checkers.models import CheckerRun
from tests.test_tasks import create_started_task, complete_submission_payload
from tests.submission_fixtures import seed_retained_submission, seed_retained_checker_run
from .test_reads import history_case


@pytest.mark.parametrize("damage", ["missing", "mismatched"])
async def test_submission_policy_custody_rejects_changes(task_client, monkeypatch, damage):
    case = await history_case(task_client, monkeypatch)
    async with db_session.get_session_factory()() as session:
        submission = await session.get(Submission, case[2])
        original = submission.locked_post_submit_checker_policy_hash
        if damage == "missing":
            submission.locked_post_submit_checker_policy_id = None
            submission.locked_post_submit_checker_policy_version = None
            submission.locked_post_submit_checker_policy_hash = None
        else:
            submission.locked_post_submit_checker_policy_hash = "sha256:" + "0" * 64
        with pytest.raises(IntegrityError):
            await session.commit()
        await session.rollback()
    async with db_session.get_session_factory()() as session:
        submission = await session.get(Submission, case[2])
        assert submission.locked_post_submit_checker_policy_hash == original
        assert submission.locked_at is not None
        assert await session.get(CheckerRun, case[3]) is not None


async def test_coherent_run_rebinding_is_rejected(task_client, monkeypatch):
    case = await history_case(task_client, monkeypatch)
    other = await create_started_task(task_client, case[0], monkeypatch, subject="other-checker-owner")
    submission_id = await seed_retained_submission(other["id"], complete_submission_payload())
    async with db_session.get_session_factory()() as session:
        original = (await session.execute(text("select to_jsonb(c) from checker_runs c where id=:id"), {"id": case[3]})).scalar_one()
        # Both parents and the version are valid: no inconsistent-pair FK shortcut.
        with pytest.raises(IntegrityError, match="checker run custody is immutable"):
            await session.execute(text("update checker_runs set task_id=:task, submission_id=:submission, submission_version=1 where id=:id"),
                                  {"task": other["id"], "submission": submission_id, "id": case[3]})
            await session.commit()
        await session.rollback()
        assert (await session.execute(text("select to_jsonb(c) from checker_runs c where id=:id"), {"id": case[3]})).scalar_one() == original


@pytest.mark.parametrize("duplicate", ["attempt", "current"])
async def test_checker_attempt_and_currentness_are_unique(task_client, monkeypatch, duplicate):
    case = await history_case(task_client, monkeypatch)
    async with db_session.get_session_factory()() as session:
        original = await session.get(CheckerRun, case[3])
        values = {column.name: getattr(original, column.name) for column in CheckerRun.__table__.columns}
        values["id"] = str(new_record_id())
        values["is_current_for_submission"] = duplicate == "current"
        values["attempt_number"] = 2 if duplicate == "current" else original.attempt_number
        session.add(CheckerRun(**values))
        expected = "uq_checker_runs_current_per_submission" if duplicate == "current" else "uq_checker_runs_submission_attempt"
        with pytest.raises(IntegrityError, match=expected):
            await session.commit()
        await session.rollback()
    async with db_session.get_session_factory()() as session:
        assert list(await session.scalars(select(CheckerRun.id).where(CheckerRun.submission_id == case[2]))) == [case[3]]


async def retained_pair(client, monkeypatch):
    case = await history_case(client, monkeypatch)
    other = await create_started_task(client, case[0], monkeypatch, subject="other-checker-owner")
    submission = await seed_retained_submission(other["id"], complete_submission_payload())
    run = await seed_retained_checker_run(submission, results=({},))
    return case, (other["id"], submission, run)


@pytest.mark.parametrize("operation", ["mismatched_insert", "coherent_update", "foreign_predecessor"])
async def test_result_and_predecessor_custody(task_client, monkeypatch, operation):
    case, other = await retained_pair(task_client, monkeypatch)
    async with db_session.get_session_factory()() as session:
        before = (await session.execute(text("select to_jsonb(r) from checker_results r where checker_run_id=:id"), {"id": other[2]})).scalar_one()
        expected = {"mismatched_insert": "fk_checker_results_run_ownership",
                    "coherent_update": "checker result custody is immutable",
                    "foreign_predecessor": "fk_checker_runs_predecessor_ownership"}[operation]
        with pytest.raises(IntegrityError, match=expected):
            if operation == "mismatched_insert":
                await session.execute(text("""insert into checker_results
                    (id,checker_run_id,task_id,submission_id,checker_name,status,severity,blocks_review,message,worker_evidence_refs,worker_visible,metadata)
                    select :id, :run, task_id, submission_id, checker_name,status,severity,blocks_review,message,worker_evidence_refs,worker_visible,metadata
                    from checker_results where checker_run_id=:source"""), {"id": str(new_record_id()), "run": case[3], "source": other[2]})
            elif operation == "coherent_update":
                await session.execute(text("update checker_results set checker_run_id=:run, task_id=:task, submission_id=:submission where checker_run_id=:source"),
                                      {"run": case[3], "task": case[1], "submission": case[2], "source": other[2]})
            else:
                source = await session.get(CheckerRun, other[2])
                values = {c.name: getattr(source, c.name) for c in CheckerRun.__table__.columns}
                values.update(id=str(new_record_id()), attempt_number=2, is_current_for_submission=False, supersedes_checker_run_id=case[3])
                session.add(CheckerRun(**values))
            await session.commit()
        await session.rollback()
        assert (await session.execute(text("select to_jsonb(r) from checker_results r where checker_run_id=:id"), {"id": other[2]})).scalar_one() == before


@pytest.mark.parametrize("table,operation", [(table, operation) for table in ("checker_runs", "checker_results") for operation in ("delete", "truncate")])
async def test_retained_rows_cannot_be_removed(task_client, monkeypatch, table, operation):
    case, other = await retained_pair(task_client, monkeypatch)
    # The first run has no results: deletion must reach custody, not a dependent FK.
    selector = "id=:id" if table == "checker_runs" else "checker_run_id=:id"
    identifier = case[3] if table == "checker_runs" else other[2]
    async with db_session.get_session_factory()() as session:
        before = (await session.execute(text(f"select to_jsonb(r) from {table} r where {selector}"), {"id": identifier})).scalar_one()
        with pytest.raises(IntegrityError, match="checker (run|result) custody is immutable"):
            await session.execute(text(f"delete from {table} where {selector}" if operation == "delete" else f"truncate {table} cascade"), {"id": identifier})
            await session.commit()
        await session.rollback()
        assert (await session.execute(text(f"select to_jsonb(r) from {table} r where {selector}"), {"id": identifier})).scalar_one() == before


@pytest.mark.parametrize("field,value", [
    ("triggered_by_subject", "substituted"), ("locked_post_submit_checker_policy_body", {}),
    ("artifact_hash_manifest", []), ("package_hash", "substituted"),
    ("attempt_number", 42), ("created_at", None),
])
async def test_run_locked_inputs_cannot_change(task_client, monkeypatch, field, value):
    case = await history_case(task_client, monkeypatch)
    async with db_session.get_session_factory()() as session:
        run = await session.get(CheckerRun, case[3])
        old = getattr(run, field)
        assert old != value
        setattr(run, field, value)
        with pytest.raises(IntegrityError, match="checker run custody is immutable"):
            await session.commit()
        await session.rollback()
        assert getattr(await session.get(CheckerRun, case[3]), field) == old


async def test_completion_and_same_parent_successor_remain_valid(task_client, monkeypatch):
    case = await history_case(task_client, monkeypatch)
    async with db_session.get_session_factory()() as session, session.begin():
        old = await session.get(CheckerRun, case[3])
        old.is_current_for_submission = False
        old.status, old.routing_recommendation, old.passed_count = "completed", "allow_review", 1
        await session.flush()
        values = {c.name: getattr(old, c.name) for c in CheckerRun.__table__.columns}
        values.update(id=str(new_record_id()), attempt_number=2, is_current_for_submission=True, supersedes_checker_run_id=old.id)
        session.add(CheckerRun(**values))
    async with db_session.get_session_factory()() as session:
        current = await session.scalar(select(CheckerRun).where(CheckerRun.submission_id == case[2], CheckerRun.is_current_for_submission.is_(True)))
        assert current.supersedes_checker_run_id == case[3] and current.attempt_number == 2
        assert (await session.get(CheckerRun, case[3])).passed_count == 1


@pytest.mark.parametrize("field", ["is_current_for_submission", "audit_event_id"])
async def test_run_custody_cannot_be_reactivated_or_reassigned(task_client, monkeypatch, field):
    from app.modules.tasks.models import AuditEvent
    case = await history_case(task_client, monkeypatch)
    async with db_session.get_session_factory()() as session:
        run = await session.get(CheckerRun, case[3])
        if field == "is_current_for_submission":
            assert run.is_current_for_submission is True
            first, replacement = False, True
        else:
            assert run.audit_event_id is None
            events = list(await session.scalars(select(AuditEvent.id).where(
                AuditEvent.project_id == case[0],
            ).order_by(AuditEvent.id).limit(2)))
            assert len(events) == 2 and events[0] != events[1]
            first, replacement = events
        setattr(run, field, first)
        await session.commit()
    async with db_session.get_session_factory()() as session:
        run = await session.get(CheckerRun, case[3])
        assert getattr(run, field) == first
        setattr(run, field, replacement)
        with pytest.raises(IntegrityError, match="checker run custody is immutable") as rejected:
            await session.commit()
        assert rejected.value.orig.sqlstate == "23514"
        await session.rollback()
        assert getattr(await session.get(CheckerRun, case[3]), field) == first
