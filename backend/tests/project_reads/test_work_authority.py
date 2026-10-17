"""Project work reads admit only a Project Manager covering the project; every denial is concealed."""

from uuid import UUID

from sqlalchemy import select

from app.core.identifiers import new_record_id
from app.db import session as db_session
from app.modules.tasks.models import AuditEvent
from tests.test_tasks import auth_headers, create_active_project, set_dev_actor
from .support import (
    AUDITOR, EXACT_MANAGER, FINANCE, MANAGER, OPERATOR, OWNER, as_admin, as_manager, get_ok, project_path,
    submitted_case,
)

READS = {
    "/submissions": "project.submission.list",
    "/assignments": "project.assignment.list",
    "/summary": "project.summary.read",
    "/task-import-batches": "project.task.import_batch.list",
}


async def _concealed(client, path):
    response = await client.get(path, headers=auth_headers())
    assert response.status_code == 404, response.text
    return response.json()["error"]["code"]


async def test_system_and_exact_project_managers_read_every_project_work_view(task_client, monkeypatch):
    project, _task, submission = await submitted_case(task_client, monkeypatch)
    as_manager(monkeypatch)
    for suffix in READS:
        await get_ok(task_client, project_path(project, suffix))
    await as_admin(task_client, monkeypatch, EXACT_MANAGER, "project_manager", project=project)
    [item] = (await get_ok(task_client, project_path(project, "/submissions")))["items"]
    assert item["submission_id"] == submission
    for suffix in READS:
        await get_ok(task_client, project_path(project, suffix))


async def test_contributor_and_other_admin_roles_are_concealed(task_client, monkeypatch):
    project, _task, _submission = await submitted_case(task_client, monkeypatch)
    absent = project_path(str(new_record_id()), "/summary")
    as_manager(monkeypatch)
    missing = await _concealed(task_client, absent)
    # Operator grants are system-scoped only; the others cover exactly this project.
    await as_admin(task_client, monkeypatch, OPERATOR, "operator")
    for subject, role in ((FINANCE, "finance_authority"), (AUDITOR, "audit_authority")):
        await as_admin(task_client, monkeypatch, subject, role, project=project)
    for subject in (OWNER, FINANCE, OPERATOR, AUDITOR):
        set_dev_actor(monkeypatch, roles="", subject=subject)
        for suffix in READS:
            assert await _concealed(task_client, project_path(project, suffix)) == missing, (subject, suffix)


async def test_exact_manager_of_another_project_is_concealed(task_client, monkeypatch):
    project, _task, _submission = await submitted_case(task_client, monkeypatch)
    as_manager(monkeypatch)
    other = await create_active_project(task_client, slug="other-managed-project")
    await as_admin(task_client, monkeypatch, EXACT_MANAGER, "project_manager", project=other["id"])
    for suffix in READS:
        assert (await task_client.get(project_path(project, suffix), headers=auth_headers())).status_code == 404
        await get_ok(task_client, project_path(other["id"], suffix))


async def test_each_read_commits_one_exact_decision(task_client, monkeypatch):
    project, _task, _submission = await submitted_case(task_client, monkeypatch)
    as_manager(monkeypatch)
    for suffix in READS:
        await get_ok(task_client, project_path(project, suffix))
    set_dev_actor(monkeypatch, roles="", subject=OWNER)
    await _concealed(task_client, project_path(project, "/submissions"))
    async with db_session.get_session_factory()() as session:
        rows = (await session.scalars(select(AuditEvent).where(
            AuditEvent.action_id.in_(tuple(READS.values())),
        ).order_by(AuditEvent.created_at))).all()
    assert [(row.action_id, row.event_type, row.permission_id) for row in rows] == [
        *((action, "SensitiveAuthorizationAllowed", "project.task.manage") for action in READS.values()),
        ("project.submission.list", "SensitiveAuthorizationDenied", "project.task.manage"),
    ]
    assert all(UUID(row.project_id) == UUID(project) for row in rows[:-1])
    assert all(row.matched_grant_id is not None for row in rows[:-1])


async def test_award_totals_need_an_exact_project_finance_grant_and_the_decision_records_it(
    task_client, monkeypatch,
):
    project, _task, _submission = await submitted_case(task_client, monkeypatch)
    as_manager(monkeypatch)
    assert (await get_ok(task_client, project_path(project, "/summary")))["award_totals"] is None
    # A system Finance grant does not disclose one project's totals.
    await as_admin(task_client, monkeypatch, MANAGER, "finance_authority")
    assert (await get_ok(task_client, project_path(project, "/summary")))["award_totals"] is None
    await as_admin(task_client, monkeypatch, MANAGER, "finance_authority", project=project)
    assert (await get_ok(task_client, project_path(project, "/summary")))["award_totals"] == []
    async with db_session.get_session_factory()() as session:
        rows = (await session.scalars(select(AuditEvent).where(
            AuditEvent.action_id == "project.summary.read",
        ).order_by(AuditEvent.created_at))).all()
    withheld, system_finance, disclosed = (row.after_facts["resource_context_digest"] for row in rows)
    # The same request records the same evidence until the evaluator locks an
    # exact-project Finance grant; that disclosure changes the recorded digest.
    assert withheld == system_finance != disclosed
    # The Project Manager grant stays the matched authority for the action.
    assert len({row.matched_grant_id for row in rows}) == 1 and rows[0].matched_grant_id is not None

