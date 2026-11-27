"""A Project Manager lists a project's ZIP preparations; findings and other roles stay out."""

from uuid import UUID

from sqlalchemy import select

from app.core.identifiers import new_record_id
from app.db import session as db_session
from app.modules.checkers.models import SelectedPreSubmitRun
from app.modules.tasks.models import AuditEvent
from tests.submission_fixtures import seed_retained_submission
from tests.test_tasks import (
    auth_headers, complete_submission_payload, create_active_project, create_started_task, set_dev_actor,
)
from .support import (
    AUDITOR, EXACT_MANAGER, FINANCE, OPERATOR, OWNER, as_admin, as_manager, get_ok, project_path, submitted_case,
)

OTHER = "worker-two"
ACTION = "project.submission_bundle_preparation.list"
def _path(project):
    return project_path(project, "/submission-bundle-preparations")


async def _runs(project):
    async with db_session.get_session_factory()() as session:
        return (await session.scalars(select(SelectedPreSubmitRun).where(
            SelectedPreSubmitRun.project_id == project,
        ).order_by(SelectedPreSubmitRun.queued_at.desc(), SelectedPreSubmitRun.id.desc()))).all()


async def _two_contributors(client, monkeypatch):
    """Two contributors' current source runs must stay outside retained history."""
    project, task, submission = await submitted_case(client, monkeypatch)
    other_task = (await create_started_task(client, project, monkeypatch, subject=OTHER))["id"]
    await seed_retained_submission(other_task, complete_submission_payload("sha256:other"))
    return project, task, submission


async def _concealed(client, path, **params):
    response = await client.get(path, params=params, headers=auth_headers())
    assert response.status_code == 404, response.text
    return response.json()["error"]["code"]


async def test_manager_and_contributor_preparation_reads_omit_current_source(task_client, monkeypatch):
    project, task, _submission = await submitted_case(task_client, monkeypatch)
    [run] = await _runs(project)
    assert run.source_operation_id is not None
    as_manager(monkeypatch)
    page = await get_ok(task_client, _path(project))
    assert page == {"items": [], "next_cursor": None}
    set_dev_actor(monkeypatch, roles="", subject=OWNER)
    assert (await get_ok(task_client, f"/api/v1/tasks/{task}/submission-bundle-preparations"))["items"] == []


async def test_outcome_filters_do_not_adopt_current_source_run(task_client, monkeypatch):
    project, _task, _submission = await submitted_case(task_client, monkeypatch)
    as_manager(monkeypatch)
    for outcome in ("passed", "pending", "failed", "infrastructure_failed"):
        assert (await get_ok(task_client, _path(project), outcome=outcome))["items"] == [], outcome
    invalid = await task_client.get(_path(project), params={"outcome": "checks_failed"}, headers=auth_headers())
    assert invalid.status_code == 422


async def test_two_contributors_current_sources_do_not_enter_historical_pages(task_client, monkeypatch):
    project, _task, _submission = await _two_contributors(task_client, monkeypatch)
    runs = await _runs(project)
    assert len(runs) == 2 and all(run.source_operation_id is not None for run in runs)
    as_manager(monkeypatch)
    first = await get_ok(task_client, _path(project), limit=1)
    assert first == {"items": [], "next_cursor": None}


async def test_system_and_exact_managers_are_admitted(task_client, monkeypatch):
    project, _task, _submission = await submitted_case(task_client, monkeypatch)
    await as_admin(task_client, monkeypatch, EXACT_MANAGER, "project_manager", project=project)
    assert (await get_ok(task_client, _path(project)))["items"] == []


async def test_contributor_and_other_admin_roles_are_concealed(task_client, monkeypatch):
    project, _task, _submission = await submitted_case(task_client, monkeypatch)
    as_manager(monkeypatch)
    missing = await _concealed(task_client, _path(str(new_record_id())))
    await as_admin(task_client, monkeypatch, OPERATOR, "operator")
    for subject, role in ((FINANCE, "finance_authority"), (AUDITOR, "audit_authority")):
        await as_admin(task_client, monkeypatch, subject, role, project=project)
    for subject in (OWNER, FINANCE, OPERATOR, AUDITOR):
        set_dev_actor(monkeypatch, roles="", subject=subject)
        assert await _concealed(task_client, _path(project)) == missing, subject
        assert await _concealed(task_client, _path(project), outcome="failed") == missing, subject


async def test_exact_manager_of_another_project_is_concealed(task_client, monkeypatch):
    project, _task, _submission = await submitted_case(task_client, monkeypatch)
    as_manager(monkeypatch)
    other = await create_active_project(task_client, slug="other-preparation-project")
    await as_admin(task_client, monkeypatch, EXACT_MANAGER, "project_manager", project=other["id"])
    await _concealed(task_client, _path(project))
    assert (await get_ok(task_client, _path(other["id"])))["items"] == []


async def test_each_read_commits_one_exact_decision(task_client, monkeypatch):
    project, _task, _submission = await submitted_case(task_client, monkeypatch)
    as_manager(monkeypatch)
    await get_ok(task_client, _path(project), outcome="failed")
    set_dev_actor(monkeypatch, roles="", subject=OWNER)
    await _concealed(task_client, _path(project))
    async with db_session.get_session_factory()() as session:
        rows = (await session.scalars(select(AuditEvent).where(
            AuditEvent.action_id == ACTION,
        ).order_by(AuditEvent.created_at))).all()
    assert [(row.event_type, row.permission_id) for row in rows] == [
        ("SensitiveAuthorizationAllowed", "project.task.manage"),
        ("SensitiveAuthorizationDenied", "project.task.manage"),
    ]
    assert UUID(rows[0].project_id) == UUID(project) and rows[0].matched_grant_id is not None
