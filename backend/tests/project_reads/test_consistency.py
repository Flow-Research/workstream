"""Each project read is one REPEATABLE READ snapshot; an owner fault is a retryable 503 that keeps nothing."""

from sqlalchemy import func, select, text
from sqlalchemy.exc import OperationalError

from app.db import session as db_session
from app.modules.tasks.models import AuditEvent
from app.modules.tasks.project_reads import ProjectWorkReader
from tests.test_tasks import auth_headers
from .support import as_manager, project_path, submitted_case


async def _decisions(action):
    async with db_session.get_session_factory()() as session:
        return await session.scalar(
            select(func.count()).select_from(AuditEvent).where(AuditEvent.action_id == action)
        )


async def test_a_project_read_runs_in_one_repeatable_read_snapshot(task_client, monkeypatch):
    project, _task, _submission = await submitted_case(task_client, monkeypatch)
    observed, original = [], ProjectWorkReader.read_submissions

    async def observing(reader, query):
        observed.append(await reader._session.scalar(text("SHOW transaction_isolation")))
        return await original(reader, query)

    monkeypatch.setattr(ProjectWorkReader, "read_submissions", observing)
    as_manager(monkeypatch)
    response = await task_client.get(project_path(project, "/submissions"), headers=auth_headers())
    assert response.status_code == 200, response.text
    assert observed == ["repeatable read"]


async def test_an_owner_fault_is_a_retryable_unavailable_read_that_rolls_back_the_decision(
    task_client, monkeypatch
):
    project, _task, _submission = await submitted_case(task_client, monkeypatch)

    async def fault(reader, query):
        raise OperationalError("SELECT 1", {}, RuntimeError("connection lost"))

    monkeypatch.setattr(ProjectWorkReader, "read_submissions", fault)
    as_manager(monkeypatch)
    response = await task_client.get(project_path(project, "/submissions"), headers=auth_headers())
    assert response.status_code == 503, response.text
    error = response.json()["error"]
    assert (error["code"], error["retryable"]) == ("project_read_unavailable", True)
    # The allowed decision was staged in the rolled-back snapshot, so no evidence remains.
    assert await _decisions("project.submission.list") == 0
