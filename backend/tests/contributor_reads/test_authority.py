"""Own-work reads conceal other contributors, ungranted projects and revoked authority."""

from uuid import UUID

from sqlalchemy import select

from app.core.identifiers import new_record_id
from app.db import session as db_session
from app.modules.authorization.models import ProjectRoleGrant
from app.modules.checkers.models import SelectedPreSubmitRun
from app.modules.tasks.models import AuditEvent
from tests.test_tasks import actor_id, auth_headers, create_started_task, set_dev_actor
from tests.submission_fixtures import seed_retained_submission
from tests.test_tasks import complete_submission_payload
from .support import ME, MANAGER, OTHER, OWNER, as_actor, get_ok, preparations_path, status_of, submitted_case

LISTS = ("assignments", "submissions")


async def _preparation(task):
    async with db_session.get_session_factory()() as session:
        return await session.scalar(select(SelectedPreSubmitRun).where(SelectedPreSubmitRun.task_id == task))


async def test_another_contributor_never_receives_the_owners_records(task_client, monkeypatch):
    project, task, _submission = await submitted_case(task_client, monkeypatch)
    preparation = await _preparation(task)
    await as_actor(task_client, monkeypatch, OTHER, grant_project=project)
    for name in LISTS:
        assert (await get_ok(task_client, f"{ME}/{name}"))["items"] == []
        assert (await get_ok(task_client, f"{ME}/{name}", project_id=project))["items"] == []
    summary = await get_ok(task_client, f"{ME}/summary", project_id=project)
    assert summary["assignments"] == {"active": 0, "closed": 0} and not any(summary["submissions"].values())
    assert await status_of(task_client, preparations_path(task)) == 404
    assert await status_of(task_client, f"{preparations_path(task)}/{preparation.id}") == 404


async def test_project_filter_without_a_submitter_grant_is_not_found(task_client, monkeypatch):
    project, _task, _submission = await submitted_case(task_client, monkeypatch)
    set_dev_actor(monkeypatch, roles="", subject=MANAGER)
    absent = str(new_record_id())
    for path in (f"{ME}/assignments", f"{ME}/submissions", f"{ME}/summary"):
        granted = await task_client.get(path, params={"project_id": project}, headers=auth_headers())
        missing = await task_client.get(path, params={"project_id": absent}, headers=auth_headers())
        assert granted.status_code == missing.status_code == 404
        assert granted.json()["error"]["code"] == missing.json()["error"]["code"]
    # The manager's own project grant lists the project, but no contributor work.
    [listed] = (await get_ok(task_client, f"{ME}/projects"))["items"]
    assert (listed["project_id"], listed["project_roles"]) == (project, [])
    assert "project_manager" in listed["admin_roles"]
    assert (await get_ok(task_client, f"{ME}/assignments"))["items"] == []


async def test_revoked_submitter_loses_every_own_work_read(task_client, monkeypatch):
    project, task, _submission = await submitted_case(task_client, monkeypatch)
    preparation = await _preparation(task)
    owner = await actor_id(OWNER)
    async with db_session.get_session_factory()() as session:
        grant = await session.scalar(select(ProjectRoleGrant.id).where(
            ProjectRoleGrant.actor_profile_id == owner, ProjectRoleGrant.status == "active",
        ))
    set_dev_actor(monkeypatch, roles="project_manager", subject=MANAGER)
    revoked = await task_client.post(
        f"/api/v1/projects/{project}/role-grants/{grant}/revoke", headers=auth_headers(),
        json={"reason": "Withdraw contributor authority"},
    )
    assert revoked.status_code == 200, revoked.text
    set_dev_actor(monkeypatch, roles="", subject=OWNER)
    for name in LISTS:
        assert (await get_ok(task_client, f"{ME}/{name}"))["items"] == []
        assert await status_of(task_client, f"{ME}/{name}", project_id=project) == 404
    assert await status_of(task_client, preparations_path(task)) == 404
    assert await status_of(task_client, f"{preparations_path(task)}/{preparation.id}") == 404
    assert (await get_ok(task_client, f"{ME}/projects"))["items"] == []


async def test_preparation_of_another_contributor_is_not_found(task_client, monkeypatch):
    project, own_task, _submission = await submitted_case(task_client, monkeypatch)
    foreign_task = (await create_started_task(task_client, project, monkeypatch, subject=OTHER))["id"]
    await seed_retained_submission(foreign_task, complete_submission_payload("sha256:foreign"))
    foreign = await _preparation(foreign_task)
    set_dev_actor(monkeypatch, roles="", subject=OWNER)
    assert await status_of(task_client, preparations_path(foreign_task)) == 404
    assert await status_of(task_client, f"{preparations_path(foreign_task)}/{foreign.id}") == 404
    assert await status_of(task_client, f"{preparations_path(own_task)}/{foreign.id}") == 404
    assert await status_of(task_client, f"{preparations_path(own_task)}/{new_record_id()}") == 404
    set_dev_actor(monkeypatch, roles="", subject=OTHER)
    assert await status_of(task_client, f"{preparations_path(foreign_task)}/{foreign.id}") == 404
    assert foreign.source_operation_id is not None
    progress = await get_ok(
        task_client, f"/api/v1/tasks/{foreign_task}/submission-operations",
        operation_id=foreign.source_operation_id,
    )
    assert progress["operation_id"] == foreign.source_operation_id


async def test_each_read_commits_its_exact_decision_and_denials(task_client, monkeypatch):
    project, _task, _submission = await submitted_case(task_client, monkeypatch)
    set_dev_actor(monkeypatch, roles="", subject=OWNER)
    await get_ok(task_client, f"{ME}/assignments", project_id=project)
    set_dev_actor(monkeypatch, roles="", subject=MANAGER)
    assert await status_of(task_client, f"{ME}/submissions", project_id=project) == 404
    async with db_session.get_session_factory()() as session:
        rows = (await session.scalars(select(AuditEvent).where(AuditEvent.action_id.in_(
            ("actor.assignment.list", "actor.submission.list"),
        )).order_by(AuditEvent.created_at))).all()
    assert [(row.action_id, row.event_type, row.permission_id) for row in rows] == [
        ("actor.assignment.list", "SensitiveAuthorizationAllowed", "submission.read_own"),
        ("actor.submission.list", "SensitiveAuthorizationDenied", "submission.read_own"),
    ]
    assert rows[0].matched_grant_id is not None and UUID(rows[0].project_id) == UUID(project)
