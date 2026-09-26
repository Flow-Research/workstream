"""Actual authority write failure and caller-owned read rollback."""

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.db import session as db_session
from app.modules.tasks.models import AuditEvent
from app.modules.tasks.submission_history import SubmissionHistoryRepository
from app.modules.audit.service import AuditService
from tests.test_tasks import auth_headers
from .test_reads import history_case


async def history_decisions():
    async with db_session.get_session_factory()() as session:
        return list(await session.scalars(select(AuditEvent.id).where(AuditEvent.action_id == "submission.read")))


@pytest.mark.parametrize("damage", ["sql", "response"])
async def test_projection_failure_rolls_back(task_client, monkeypatch, damage):
    _, _, submission, _ = await history_case(task_client, monkeypatch)
    original = SubmissionHistoryRepository.read
    called = []
    async def fail(owner, *args, **kwargs):
        await original(owner, *args, **kwargs)
        # A real decision has been flushed in this transaction, not committed.
        assert await owner._session.scalar(select(AuditEvent.id).where(AuditEvent.action_id == "submission.read"))
        called.append(True)
        if damage == "sql":
            raise SQLAlchemyError("projection storage unavailable")
        from app.modules.tasks.api.submission_history import ContributorSubmissionHistory
        return [ContributorSubmissionHistory.model_validate({"id": submission})], False
    with monkeypatch.context() as patch:
        patch.setattr(SubmissionHistoryRepository, "read", fail)
        response = await task_client.get(f"/api/v1/submissions/{submission}", headers=auth_headers())
    assert called == [True]
    assert response.status_code == 503 and response.json()["error"]["retryable"]
    assert await history_decisions() == []
    assert (await task_client.get(f"/api/v1/submissions/{submission}", headers=auth_headers())).status_code == 200
    assert len(await history_decisions()) == 1


async def test_audit_insert_failure_rolls_back(task_client, monkeypatch):
    _, _, submission, _ = await history_case(task_client, monkeypatch)
    original = AuditService.add_authority_event
    attempted = []
    async def fail(service, value):
        if value.action_id == "submission.read":
            await service._repository._session.execute(text(
                "ALTER TABLE audit_events ADD CONSTRAINT test_reject_history_audit "
                "CHECK (action_id <> 'submission.read') NOT VALID"
            ))
            try:
                await original(service, value)
            except IntegrityError as exc:
                assert "INSERT INTO audit_events" in exc.statement
                assert exc.orig.sqlstate == "23514"
                assert "test_reject_history_audit" in str(exc.orig)
                attempted.append(True)
                raise
            raise AssertionError("audit insert unexpectedly succeeded")
        return await original(service, value)
    async def forbidden(*args, **kwargs):
        pytest.fail("projection after failed authorization insert")
    with monkeypatch.context() as patch:
        patch.setattr(AuditService, "add_authority_event", fail)
        patch.setattr(SubmissionHistoryRepository, "read", forbidden)
        response = await task_client.get(f"/api/v1/submissions/{submission}", headers=auth_headers())
    assert attempted == [True]
    assert response.status_code == 503 and response.json()["error"]["retryable"]
    assert await history_decisions() == []
    assert (await task_client.get(f"/api/v1/submissions/{submission}", headers=auth_headers())).status_code == 200


async def test_authority_unavailable(task_client, monkeypatch):
    from app.modules.authorization.history_authorization import HistoryReadAuthorization
    from app.modules.authorization.runtime import AuthorizationEvidenceUnavailable
    _, _, submission, _ = await history_case(task_client, monkeypatch)
    async def unavailable(*args, **kwargs):
        raise AuthorizationEvidenceUnavailable("history authority unavailable")
    async def forbidden(*args, **kwargs):
        pytest.fail("projection without authority")
    with monkeypatch.context() as patch:
        patch.setattr(HistoryReadAuthorization, "require_history", unavailable)
        patch.setattr(SubmissionHistoryRepository, "read", forbidden)
        response = await task_client.get(f"/api/v1/submissions/{submission}", headers=auth_headers())
    assert response.status_code == 503 and response.json()["error"]["retryable"]
    assert await history_decisions() == []
    assert (await task_client.get(f"/api/v1/submissions/{submission}", headers=auth_headers())).status_code == 200
