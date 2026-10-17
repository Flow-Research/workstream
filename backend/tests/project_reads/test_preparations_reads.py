"""A Project Manager lists a project's ZIP preparations; findings and other roles stay out."""

from uuid import UUID

from sqlalchemy import select

from app.core.identifiers import new_record_id
from app.db import session as db_session
from app.modules.checkers.models import SelectedPreSubmitRun
from app.modules.tasks.models import AuditEvent
from tests.submission_fixtures import seed_retained_submission
from tests.test_tasks import (
    actor_id, auth_headers, complete_submission_payload, create_active_project, create_started_task, set_dev_actor,
)
from .support import (
    AUDITOR, EXACT_MANAGER, FINANCE, OPERATOR, OWNER, as_admin, as_manager, get_ok, project_path, submitted_case,
)

OTHER = "worker-two"
ACTION = "project.submission_bundle_preparation.list"
# The summary fields plus the contributor; no findings, packet or file content.
FIELDS = {
    "preparation_id", "task_id", "assignment_id", "outcome", "state", "storage_status",
    "infrastructure_failure_code", "archive_sha256", "archive_byte_count", "finding_counts", "admission_id",
    "submission_id", "created_at", "completed_at", "actor_profile_id",
}


def _path(project):
    return project_path(project, "/submission-bundle-preparations")


async def _runs(project):
    async with db_session.get_session_factory()() as session:
        return (await session.scalars(select(SelectedPreSubmitRun).where(
            SelectedPreSubmitRun.project_id == project,
        ).order_by(SelectedPreSubmitRun.queued_at.desc(), SelectedPreSubmitRun.id.desc()))).all()


async def _two_contributors(client, monkeypatch):
    """worker-one's and worker-two's submitted preparations in one project."""
    project, task, submission = await submitted_case(client, monkeypatch)
    other_task = (await create_started_task(client, project, monkeypatch, subject=OTHER))["id"]
    await seed_retained_submission(other_task, complete_submission_payload("sha256:other"))
    return project, task, submission


async def _concealed(client, path, **params):
    response = await client.get(path, params=params, headers=auth_headers())
    assert response.status_code == 404, response.text
    return response.json()["error"]["code"]


async def test_manager_reads_counts_and_contributor_without_findings(task_client, monkeypatch):
    project, task, submission = await submitted_case(task_client, monkeypatch)
    [run] = await _runs(project)
    as_manager(monkeypatch)
    page = await get_ok(task_client, _path(project))
    assert page["next_cursor"] is None
    [item] = page["items"]
    assert set(item) == FIELDS
    assert (item["preparation_id"], item["task_id"], item["submission_id"]) == (run.id, task, submission)
    assert UUID(item["actor_profile_id"]) == UUID(str(await actor_id(OWNER)))
    assert (item["outcome"], item["state"]) == ("passed", "submitted")
    assert set(item["finding_counts"]) == {"blocking", "warning", "coverage_incomplete"}
    # The same projection the contributor reads for their own preparation.
    set_dev_actor(monkeypatch, roles="", subject=OWNER)
    [own] = (await get_ok(task_client, f"/api/v1/tasks/{task}/submission-bundle-preparations"))["items"]
    assert own == {key: value for key, value in item.items() if key != "actor_profile_id"}


async def test_outcome_filter_selects_the_stored_outcome(task_client, monkeypatch):
    project, _task, _submission = await submitted_case(task_client, monkeypatch)
    as_manager(monkeypatch)
    assert len((await get_ok(task_client, _path(project), outcome="passed"))["items"]) == 1
    for outcome in ("pending", "failed", "infrastructure_failed"):
        assert (await get_ok(task_client, _path(project), outcome=outcome))["items"] == [], outcome
    invalid = await task_client.get(_path(project), params={"outcome": "checks_failed"}, headers=auth_headers())
    assert invalid.status_code == 422


async def test_pages_are_newest_first_without_gaps_or_duplicates(task_client, monkeypatch):
    project, _task, _submission = await _two_contributors(task_client, monkeypatch)
    expected = [run.id for run in await _runs(project)]
    assert len(expected) == 2
    as_manager(monkeypatch)
    first = await get_ok(task_client, _path(project), limit=1)
    assert first["next_cursor"] is not None
    second = await get_ok(task_client, _path(project), limit=1, cursor=first["next_cursor"])
    assert second["next_cursor"] is None
    assert [item["preparation_id"] for item in first["items"] + second["items"]] == expected
    assert {item["actor_profile_id"] for item in first["items"] + second["items"]} == {
        str(await actor_id(OWNER)), str(await actor_id(OTHER)),
    }
    # A cursor is bound to its exact filters and limit.
    for params in ({"limit": 2}, {"limit": 1, "outcome": "passed"}):
        response = await task_client.get(
            _path(project), params=params | {"cursor": first["next_cursor"]}, headers=auth_headers(),
        )
        assert response.status_code == 422, params
        assert response.json()["error"]["code"] == "project_read_cursor_invalid"


async def test_system_and_exact_managers_are_admitted(task_client, monkeypatch):
    project, _task, _submission = await submitted_case(task_client, monkeypatch)
    await as_admin(task_client, monkeypatch, EXACT_MANAGER, "project_manager", project=project)
    assert len((await get_ok(task_client, _path(project)))["items"]) == 1


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
