"""Probe revision custody during real T5, before its Submission INSERT."""

import json
from contextlib import asynccontextmanager, contextmanager
from unittest.mock import patch

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.core.identifiers import new_record_id
from app.modules.tasks.repository import TaskRepository


@asynccontextmanager
async def _probe_savepoint(session):
    # ROLLBACK TO alone leaves PostgreSQL inside the savepoint. Explicit release
    # restores the root transaction required by the subsequent checker owner.
    await session.execute(text("SAVEPOINT revision_probe"))
    try:
        yield
    finally:
        await session.execute(text("ROLLBACK TO SAVEPOINT revision_probe"))
        await session.execute(text("RELEASE SAVEPOINT revision_probe"))


@contextmanager
def probe_revision_insert():
    """Keep the real transaction and insertion; reject forged composite inputs."""
    original = TaskRepository.add_submission
    observed = []

    async def add(repository, submission):
        if submission.supersedes_submission_id is None:
            return await original(repository, submission)
        session = repository._session
        record = {column.name: getattr(submission, column.key)
                  for column in submission.__table__.columns}
        query = text("""
            SELECT public.accepted_revision_submission_valid(
                jsonb_populate_record(NULL::public.submissions, CAST(:record AS jsonb)), false)
        """)
        assert await session.scalar(query, {"record": json.dumps(record, default=str)}) is True
        for field, value in (
            ("task_assignment_id", str(new_record_id())),
            ("supersedes_submission_id", str(new_record_id())),
            ("locked_review_policy_hash", "sha256:" + "0" * 64),
        ):
            with pytest.raises(IntegrityError, match="accepted revision submission custody mismatch"):
                async with _probe_savepoint(session):
                    await session.execute(query, {"record": json.dumps(record | {field: value}, default=str)})
        admission = await session.scalar(text("""
            SELECT to_jsonb(a) FROM public.submission_bundle_admissions a
            JOIN public.workstream_tasks t ON t.active_submission_operation_id=a.source_operation_id
            WHERE t.id=:task
        """), {"task": submission.task_id})
        assert admission is not None
        source_query = text("""
            SELECT public.require_source_submission_admission(jsonb_populate_record(
                NULL::public.submission_bundle_admissions, CAST(:record AS jsonb)))
        """)
        await session.execute(source_query, {"record": json.dumps(admission)})
        for field in ("source_operation_id", "revision_preparation_id", "predecessor_submission_id",
                      "checker_remediation_manifest_id"):
            with pytest.raises(IntegrityError, match="source admission"):
                async with _probe_savepoint(session):
                    await session.execute(source_query, {
                        "record": json.dumps(admission | {field: str(new_record_id())}),
                    })
        observed.append(submission.id)
        return await original(repository, submission)

    with patch.object(TaskRepository, "add_submission", add):
        yield observed
    assert len(observed) == 1


@contextmanager
def stale_fence_before_acceptance_commit():
    """Reserve a legitimate successor after T4 staging, before deferred SQL checks."""
    from app.adapters.checkers import evaluation_coordinator
    from app.modules.artifacts.intake.foreground_admission import ForegroundIntakeAdmission
    from tests.checkers.execution.storage_fixture import storage_request

    original = ForegroundIntakeAdmission._accept_new
    observed = []

    async def accept(admission, session, authority, repository, row, owner,
                     request, terminal_digest, checkers, outbox):
        receipt = await original(admission, session, authority, repository, row, owner,
                                 request, terminal_digest, checkers, outbox)
        predecessor = row.accepted_context["predecessor_submission_id"]
        assert predecessor is not None and row.state == "finalization_pending"
        successor = await storage_request(session, predecessor, generation=2)
        reserved = await evaluation_coordinator(session).reserve_current_evaluation(successor)
        assert reserved.request_id == successor.evaluation_request_id
        observed.append(row.id)
        return receipt

    with patch.object(ForegroundIntakeAdmission, "_accept_new", accept):
        yield observed
    assert len(observed) == 1
