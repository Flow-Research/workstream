"""Public history keeps fixed facts, task isolation and live bounded continuation."""
import json
from datetime import timedelta

import pytest
from sqlalchemy import select

from app.core.identifiers import new_record_id
from app.db import session as db_session
from app.modules.tasks.lifecycle import ALLOWED_TASK_TRANSITIONS
from app.modules.tasks.models import WorkstreamTask
from tests.authorization.task_reads.support import task_case, create_task
from tests.authorization.task_audit_evidence.support import FIELDS, grant_audit, path
from tests.tasks.test_audit_evidence import NOW, store_event


async def test_all_task_states(admin_access, monkeypatch):
    from app.modules.tasks.service import TaskService
    project, manager, task = await task_case(admin_access)
    await grant_audit(admin_access, project)
    async def no_policy_read(*args, **kwargs):
        raise AssertionError("history tried to validate a policy body")
    monkeypatch.setattr(TaskService, "_load_locked_task_context", no_policy_read)
    states = {state for transition in ALLOWED_TASK_TRANSITIONS for state in transition}
    assert len(states) == 9
    for state in sorted(states):
        async with db_session.get_session_factory()() as session, session.begin():
            row = await session.get(WorkstreamTask, str(task))
            row.status = state
        response = await admin_access.signed.client.get(path(project, task), headers=admin_access.target.headers)
        assert response.status_code == 200, (state, response.text)
        assert response.json()["items"]
    draft = await create_task(admin_access, project, manager, ready=False)
    response = await admin_access.signed.client.get(path(project, draft), headers=admin_access.target.headers)
    assert response.status_code == 200 and len(response.json()["items"]) == 1


async def test_state_guard_probe(admin_access, monkeypatch):
    from app.modules.authorization.domain import task_authority as owner
    from app.modules.authorization.catalogue import ActionId
    original = owner.task_resource_guard
    def ready_only(action, resource):
        return original(action, resource) and (action is not ActionId.AUDIT_TASK_EVIDENCE_READ or resource.task_status == "ready")
    monkeypatch.setattr(owner, "task_resource_guard", ready_only)
    with pytest.raises(AssertionError, match="claimed") as error:
        await test_all_task_states(admin_access, monkeypatch)
    assert "404 == 200" in str(error.value)


async def test_history_pagination_and_privacy(admin_access):
    project, manager, task = await task_case(admin_access, ready=False)
    sibling = await create_task(admin_access, project, manager, ready=False)
    other, _, foreign = await task_case(admin_access, ready=False)
    assert other != project
    await grant_audit(admin_access, project)
    expected = []
    async with db_session.get_session_factory()() as session, session.begin():
        for _ in range(3):
            for decoy in (sibling, foreign):
                await store_event(session, str(decoy))
            await store_event(session, str(task), entity_type="submission")
            row = await store_event(session, str(task))
            expected.append(row.id)
        source = await session.get(WorkstreamTask, str(task))
        empty = WorkstreamTask(id=str(new_record_id()), project_id=str(project), title="empty", description="empty",
                              source_type=source.source_type, status="draft", created_by=source.created_by)
        session.add(empty)
        empty_id = empty.id
    expected.sort()
    cursor = dict(project_id=str(project), task_id=str(task), created_at=(NOW - timedelta(seconds=1)).isoformat(), event_id=str(new_record_id()))
    observed = []
    for index in range(3):
        response = await admin_access.signed.client.get(path(project, task), headers=admin_access.target.headers,
            params={"limit": 1, "cursor": json.dumps(cursor)})
        assert response.status_code == 200, response.text
        body = response.json()
        assert len(body["items"]) == 1
        item = body["items"][0]
        assert set(item) == FIELDS
        assert item["actor_id"] == "recorded-actor" and item["event_type"] == "fixture_event"
        assert "private" not in response.text
        assert item["assignment_id"] is item["authorization_decision_id"] is None
        observed.append(item["event_id"])
        cursor = body["next_cursor"]
        assert (cursor is None) is (index == 2)
    assert observed == expected
    cursor = dict(project_id=str(project), task_id=str(task), created_at=NOW.isoformat(), event_id=expected[-1])
    response = await admin_access.signed.client.get(path(project, task), headers=admin_access.target.headers, params={"cursor": json.dumps(cursor)})
    assert response.status_code == 200 and response.json()["items"] == [] and response.json()["next_cursor"] is None
    response = await admin_access.signed.client.get(path(project, empty_id), headers=admin_access.target.headers)
    assert response.status_code == 200 and response.json()["items"] == []
    for change in ({"project_id": str(other)}, {"task_id": str(sibling)}):
        response = await admin_access.signed.client.get(path(project, task), headers=admin_access.target.headers, params={"cursor": json.dumps(cursor | change)})
        assert response.status_code == 422


async def test_invalid_reference_is_sanitized(admin_access):
    project, _, task = await task_case(admin_access)
    await grant_audit(admin_access, project)
    async with db_session.get_session_factory()() as session, session.begin():
        row = await store_event(session, str(task), when=NOW, event_type="TaskClaimed", typed_source=True,
            payload={"references": {"project_id": str(project), "task_id": str(task),
                                    "assignment_id": "private-invalid", "authorization_decision_id": str(new_record_id())}})
        assert await session.scalar(select(type(row).id).where(type(row).id == row.id)) == row.id
    response = await admin_access.signed.client.get(path(project, task), headers=admin_access.target.headers)
    assert response.status_code == 422, response.text
    assert response.json()["detail"] == "task audit evidence is invalid"
    assert "private-invalid" not in response.text
