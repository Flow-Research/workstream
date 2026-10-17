"""Finance lists every ContributionPolicy version of a project; other roles are concealed."""

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

ACTION = "contribution.policy.list"


def _path(project, suffix=""):
    return project_path(project, f"/contribution-policies{suffix}")


async def _concealed(client, path):
    response = await client.get(path, headers=auth_headers())
    assert response.status_code == 404, response.text
    return response.json()["error"]["code"]


async def _with_successor_draft(client, monkeypatch):
    """An active project's published version 1 and Finance's successor draft version 2."""
    project = (await create_active_project(client))["id"]
    await as_admin(client, monkeypatch, FINANCE, "finance_authority", project=project)
    created = await client.post(
        _path(project, "/drafts"), json={"name": "Successor"},
        headers=auth_headers() | {"Idempotency-Key": str(new_record_id())},
    )
    assert created.status_code == 201, created.text
    return project, created.json()


async def test_finance_pages_every_version_oldest_first(task_client, monkeypatch):
    project, draft = await _with_successor_draft(task_client, monkeypatch)
    first = await get_ok(task_client, _path(project), limit=1)
    assert first["next_cursor"] is not None
    second = await get_ok(task_client, _path(project), limit=1, cursor=first["next_cursor"])
    assert second["next_cursor"] is None
    published, successor = first["items"] + second["items"]
    assert (published["version_number"], published["version_status"], published["policy_status"]) == (
        1, "published", "active",
    )
    assert published["published_at"] is not None and published["retired_at"] is None
    assert (successor["version_number"], successor["version_status"]) == (2, "draft")
    assert successor["contribution_policy_version_id"] == draft["contribution_policy_version_id"]
    assert successor["published_at"] is None and successor["created_at"] >= published["created_at"]
    assert (await get_ok(task_client, _path(project), limit=2))["items"] == [published, successor]
    # Each item is the exact-version read plus its lifecycle instants.
    for item in (published, successor):
        exact = await get_ok(
            task_client, _path(project, f"/{item['contribution_policy_id']}"),
            version_id=item["contribution_policy_version_id"],
        )
        assert exact == {key: value for key, value in item.items()
                         if key not in {"created_at", "published_at", "retired_at"}}
    # A cursor is bound to its exact limit.
    tampered = await task_client.get(
        _path(project), params={"limit": 2, "cursor": first["next_cursor"]}, headers=auth_headers(),
    )
    assert tampered.status_code == 422
    assert tampered.json()["error"]["code"] == "project_read_cursor_invalid"


async def test_project_manager_contributor_and_other_roles_are_concealed(task_client, monkeypatch):
    project, _task, _submission = await submitted_case(task_client, monkeypatch)
    await as_admin(task_client, monkeypatch, FINANCE, "finance_authority", project=project)
    assert len((await get_ok(task_client, _path(project)))["items"]) == 1
    missing = await _concealed(task_client, _path(str(new_record_id())))
    await as_admin(task_client, monkeypatch, OPERATOR, "operator")
    for subject, role in ((EXACT_MANAGER, "project_manager"), (AUDITOR, "audit_authority")):
        await as_admin(task_client, monkeypatch, subject, role, project=project)
    for subject in (MANAGER, EXACT_MANAGER, OWNER, OPERATOR, AUDITOR):
        set_dev_actor(monkeypatch, roles="", subject=subject)
        assert await _concealed(task_client, _path(project)) == missing, subject
    # The existing current and exact reads are unchanged by the list route.
    set_dev_actor(monkeypatch, roles="", subject=FINANCE)
    assert (await get_ok(task_client, _path(project, "/current")))["current_published_version_id"]


async def test_finance_of_another_project_is_concealed(task_client, monkeypatch):
    project = (await create_active_project(task_client))["id"]
    as_manager(monkeypatch)
    other = (await create_active_project(task_client, slug="other-policy-project"))["id"]
    await as_admin(task_client, monkeypatch, FINANCE, "finance_authority", project=other)
    await _concealed(task_client, _path(project))
    assert len((await get_ok(task_client, _path(other)))["items"]) == 1


async def test_each_read_commits_one_exact_decision(task_client, monkeypatch):
    project = (await create_active_project(task_client))["id"]
    await as_admin(task_client, monkeypatch, FINANCE, "finance_authority", project=project)
    await get_ok(task_client, _path(project))
    as_manager(monkeypatch)
    await _concealed(task_client, _path(project))
    async with db_session.get_session_factory()() as session:
        rows = (await session.scalars(select(AuditEvent).where(
            AuditEvent.action_id == ACTION,
        ).order_by(AuditEvent.created_at))).all()
    assert [(row.event_type, row.permission_id) for row in rows] == [
        ("SensitiveAuthorizationAllowed", "compensation.policy.manage"),
        ("SensitiveAuthorizationDenied", "compensation.policy.manage"),
    ]
    assert UUID(rows[0].project_id) == UUID(project) and rows[0].matched_grant_id is not None


async def test_list_keeps_a_retired_version_with_its_retirement_instant(task_client, monkeypatch):
    project = (await create_active_project(task_client))["id"]
    await as_admin(task_client, monkeypatch, FINANCE, "finance_authority", project=project)
    [published] = (await get_ok(task_client, _path(project)))["items"]
    retired = await task_client.post(
        _path(project, f"/{published['contribution_policy_id']}/versions/"
                       f"{published['contribution_policy_version_id']}/retirement"),
        json={}, headers=auth_headers() | {"Idempotency-Key": str(new_record_id())},
    )
    assert retired.status_code == 200, retired.text
    [item] = (await get_ok(task_client, _path(project)))["items"]
    assert item["contribution_policy_version_id"] == published["contribution_policy_version_id"]
    assert (item["version_status"], item["policy_status"]) == ("retired", "retired")
    assert item["published_at"] == published["published_at"] and item["retired_at"] is not None
    assert item["retired_at"] >= item["published_at"]
