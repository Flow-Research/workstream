"""Queue authorization evidence, rollback and observed PostgreSQL lock ordering."""

from hashlib import sha256
from uuid import UUID

import pytest
from sqlalchemy import event, select

from app.core.hashing import canonical_json_hash
from app.db import session as db_session
from app.modules.authorization.catalogue import ActionId
from app.modules.authorization.domain.task_queues import QueueReadResourceContext
from app.modules.authorization.pagination import authorization_read_query_digest
from app.modules.authorization.runtime import authorization_resource_digest
from app.modules.tasks.models import AuditEvent
from app.modules.tasks.repository import TaskRepository
from app.modules.tasks.schemas import ManagementTaskQueueResponse
from tests.authorization.task_queues.support import ACTIONS, PATHS
from tests.tasks.test_public_queues import queue_actor
from tests.test_tasks import (
    task_database_env as task_database_env, task_client as task_client,
    create_active_project, create_ready_task, auth_headers,
)


async def decisions(project, kind="management"):
    async with db_session.get_session_factory()() as session:
        return list(await session.scalars(select(AuditEvent).where(
            AuditEvent.project_id == project, AuditEvent.action_id == ACTIONS[kind],
        ).order_by(AuditEvent.created_at)))


async def test_queue_records_exact_page_authority(task_client):
    project = await create_active_project(task_client)
    for _ in range(2):
        await create_ready_task(task_client, project["id"])
    path = PATHS["management"].format(project=project["id"])
    first = await task_client.get(path, params={"limit": 1}, headers=auth_headers())
    assert first.status_code == 200, first.text
    cursor = first.json()["next_cursor"]
    assert cursor is not None
    second = await task_client.get(path, params={"limit": 1, "cursor": cursor}, headers=auth_headers())
    assert second.status_code == 200, second.text
    rows = await decisions(project["id"])
    assert len(rows) == 2
    for row, presented in zip(rows, (None, cursor), strict=True):
        request_digest = canonical_json_hash({
            "query_digest": authorization_read_query_digest(
                action_id=ActionId.PROJECT_TASK_QUEUE_READ, project_id=UUID(project["id"]), limit=1,
            ),
            "presented_cursor_digest": "sha256:" + sha256(presented.encode()).hexdigest() if presented else None,
        })
        expected = authorization_resource_digest(QueueReadResourceContext(
            resource_id=UUID(project["id"]), scope_project_id=UUID(project["id"]), request_digest=request_digest,
        ))
        assert row.after_facts == {"allowed": True, "resource_context_digest": expected}
        assert row.resource_id == row.project_id == project["id"]
        assert row.permission_id == "project.task.manage" and row.matched_grant_id is not None
    assert rows[0].after_facts != rows[1].after_facts
    bad = await task_client.get(path, params={"limit": 1, "cursor": "bad"}, headers=auth_headers())
    assert bad.status_code == 422
    assert len(await decisions(project["id"])) == 2


@pytest.mark.parametrize("failure", ["projection", "serialization", "audit"])
async def test_queue_failure_rolls_back_allow(task_client, monkeypatch, failure):
    project = await create_active_project(task_client)
    path = PATHS["management"].format(project=project["id"])
    assert (await task_client.get(path, headers=auth_headers())).status_code == 200
    before = [row.id for row in await decisions(project["id"])]
    if failure == "projection":
        async def broken(*args, **kwargs):
            raise RuntimeError("projection failure")
        monkeypatch.setattr(TaskRepository, "read_management_tasks", broken)
    elif failure == "serialization":
        def broken(*args, **kwargs):
            raise RuntimeError("serialization failure")
        monkeypatch.setattr(ManagementTaskQueueResponse, "model_dump", broken)
    else:
        from app.modules.audit.service import AuditService
        from app.modules.authorization.runtime import AuthorizationEvidenceUnavailable
        async def broken(*args, **kwargs):
            raise AuthorizationEvidenceUnavailable("audit failure")
        monkeypatch.setattr(AuditService, "add_authority_event", broken)
    if failure == "audit":
        response = await task_client.get(path, headers=auth_headers())
        assert response.status_code == 503
    else:
        response = await task_client.get(path, headers=auth_headers())
        assert response.status_code == 500, response.text
    assert [row.id for row in await decisions(project["id"])] == before


@pytest.mark.parametrize("kind", PATHS)
async def test_queue_lock_order(task_client, monkeypatch, kind):
    project = await create_active_project(task_client)
    await create_ready_task(task_client, project["id"])
    await queue_actor(task_client, monkeypatch, project["id"], kind)
    engine = db_session.get_session_factory().kw["bind"].sync_engine
    statements = []

    def capture(conn, cursor, statement, parameters, context, many):
        statements.append(statement.lower())

    event.listen(engine, "before_cursor_execute", capture)
    try:
        response = await task_client.get(PATHS[kind].format(project=project["id"]), headers=auth_headers())
        assert response.status_code == 200, response.text
    finally:
        event.remove(engine, "before_cursor_execute", capture)
    def assert_order():
        locks = [statement for statement in statements if "for update" in statement]
        tables = ["actor_profiles", "actor_identity_links", "project_role_grants" if kind == "ready" else "admin_role_grants", "projects"]
        positions = [next(i for i, sql in enumerate(locks) if "from " + table + " " in sql.replace("\n", " ")) for table in tables]
        assert positions == sorted(positions) and len(set(positions)) == 4, "project must follow matched grant"
        task_selects = [sql for sql in statements if "from workstream_tasks" in sql]
        assert len(task_selects) == 1 and "for update" not in task_selects[0]
        assert statements.index(task_selects[0]) > statements.index(locks[positions[-1]])

    assert_order()
    # Deliberately acquire Project before the matched grant, recreating the lock-order defect.
    from app.modules.authorization.repository import AdminAuthorizationRepository
    method = "find_active_project_role_any" if kind == "ready" else "find_effective_grant"
    original = getattr(AdminAuthorizationRepository, method)

    async def reversed_locks(repository, *args, **kwargs):
        await repository.lock_project(UUID(project["id"]))
        return await original(repository, *args, **kwargs)

    monkeypatch.setattr(AdminAuthorizationRepository, method, reversed_locks)
    statements.clear()
    event.listen(engine, "before_cursor_execute", capture)
    try:
        response = await task_client.get(PATHS[kind].format(project=project["id"]), headers=auth_headers())
        assert response.status_code == 200, response.text
    finally:
        event.remove(engine, "before_cursor_execute", capture)
    with pytest.raises(AssertionError, match="project must follow matched grant"):
        assert_order()
