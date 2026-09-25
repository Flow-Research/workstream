"""Public shape and adversarial request boundaries before product work."""
import json
from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from app.core.identifiers import new_record_id
from app.main import create_app
from app.modules.authorization.catalogue import ActionId
from app.modules.authorization.domain.task_authority import TaskAuthorityResourceContext, task_resource_guard
from app.modules.tasks import router as owner
from app.modules.tasks.authorized_commands import AuthorizedTaskCommands
from app.modules.tasks.service import TaskService, TaskValidationError
from tests.authorization.task_audit_evidence.support import ACTION, FIELDS, path


def test_public_contract():
    schema = create_app().openapi()
    operation = schema["paths"][path("{project_id}", "{task_id}")]["get"]
    assert operation["x-workstream-action-id"] == ACTION
    assert "/api/v1/tasks/{task_id}/audit-events" not in schema["paths"]
    assert "AuditEventResponse" not in schema["components"]["schemas"]
    assert set(schema["components"]["schemas"]["AuditTaskEvidence"]["properties"]) == FIELDS
    assert not hasattr(TaskService, "list_task_audit_events")
    assert not hasattr(TaskService, "_audit_response")
    assert operation["responses"]["200"]["content"]["application/json"]["schema"] == {"$ref": "#/components/schemas/AuditTaskEvidencePage"}


def test_cursor_validation(monkeypatch):
    project, task, event = new_record_id(), new_record_id(), new_record_id()
    value = dict(project_id=str(project), task_id=str(task), created_at=datetime.now(UTC).isoformat(), event_id=str(event))
    request = owner.task_evidence_request(project, task, 1, json.dumps(value))
    assert request.after.event_id == event and request.limit == 1
    assert owner.task_evidence_request(project, task).after is None
    raw = json.dumps(value)
    invalid = ["", "[]", "null", "[" * 600, raw + " " * 513, raw[:-1] + ',"event_id":"' + str(event) + '"}']
    for field, replacement in (("project_id", str(new_record_id())), ("task_id", str(new_record_id())),
                               ("event_id", "bad"), ("created_at", "2026-01-01T00:00:00"),
                               ("created_at", "2026-01-01T00:00:00+99:99"), ("extra", "bad"), ("event_id", {})):
        invalid.append(json.dumps(value | {field: replacement}))
    invalid.append(json.dumps({key: item for key, item in value.items() if key != "event_id"}))
    for cursor in invalid:
        with pytest.raises(HTTPException) as error:
            owner.task_evidence_request(project, task, 1, cursor)
        assert error.value.status_code == 422 and error.value.detail == "task evidence request is invalid"
    for limit in (0, 101, True, "1"):
        with pytest.raises(HTTPException):
            owner.task_evidence_request(project, task, limit)
    original = owner.json.loads
    def no_large_decode(raw, **kwargs):
        assert len(raw) <= 512, "oversized cursor reached decoder"
        return original(raw, **kwargs)
    monkeypatch.setattr(owner.json, "loads", no_large_decode)
    with pytest.raises(HTTPException):
        owner.task_evidence_request(project, task, 1, raw + " " * 513)


def test_cursor_cap_probe(monkeypatch):
    monkeypatch.setattr(owner, "TASK_EVIDENCE_CURSOR_LIMIT", 10000)
    with pytest.raises(pytest.fail.Exception, match="DID NOT RAISE"):
        test_cursor_validation(monkeypatch)


async def test_http_cursor_rejection_before_task(admin_access):
    from app.api.deps.authorization import get_task_commands
    app = admin_access.signed.client._transport.app
    project, task = new_record_id(), new_record_id()
    value = dict(project_id=str(project), task_id=str(task),
                 created_at=datetime.now(UTC).isoformat(), event_id=str(new_record_id()))
    raw = json.dumps(value)
    invalid = ["{", raw + " " * 513,
               json.dumps(value | {"project_id": str(new_record_id())}),
               json.dumps(value | {"task_id": str(new_record_id())}),
               raw[:-1] + ',"event_id":"' + value["event_id"] + '"}']
    reached = []
    async def forbidden():
        reached.append(True)
        raise HTTPException(status_code=418, detail="TASK composition reached")
    app.dependency_overrides[get_task_commands] = forbidden
    try:
        for cursor in invalid:
            response = await admin_access.signed.client.get(path(project, task),
                headers=admin_access.target.headers, params={"cursor": cursor})
            assert response.status_code == 422, response.text
            assert response.json()["detail"] == "task evidence request is invalid"
            assert not reached
        # A valid cursor and the same signed actor reach the observed dependency.
        response = await admin_access.signed.client.get(path(project, task),
            headers=admin_access.target.headers, params={"cursor": raw})
        assert response.status_code == 418
        assert response.json()["detail"] == "TASK composition reached"
        assert reached == [True]
    finally:
        app.dependency_overrides.pop(get_task_commands)


async def test_http_cursor_cap_probe(admin_access, monkeypatch):
    monkeypatch.setattr(owner, "TASK_EVIDENCE_CURSOR_LIMIT", 10000)
    with pytest.raises(AssertionError, match="418 == 422"):
        await test_http_cursor_rejection_before_task(admin_access)


def test_command_field_guard():
    resource = TaskAuthorityResourceContext(resource_id=new_record_id(), scope_project_id=new_record_id(),
        actor_profile_id=new_record_id(), identity_link_id=new_record_id(), task_status="draft",
        assigned_to=None, assignment_id=None, assignment_contributor_id=None,
        locked_context_hash="sha256:" + "a" * 64, reason=None)
    action = ActionId(ACTION)
    assert task_resource_guard(action, resource)
    for field, value in (("idempotency_key", new_record_id()), ("replay_assignment_id", new_record_id()),
                         ("request_digest", "sha256:" + "b" * 64), ("replay_command_id", new_record_id())):
        assert not task_resource_guard(action, resource.model_copy(update={field: value})), field


def test_command_guard_probe(monkeypatch):
    from app.modules.authorization.domain import task_authority
    monkeypatch.setattr(task_authority, "TASK_CONCEALED_READ_ACTIONS", task_authority.TASK_CONCEALED_READ_ACTIONS - {ActionId(ACTION)})
    with pytest.raises(AssertionError, match="idempotency_key"):
        test_command_field_guard()


async def test_invalid_request_before_transaction():
    session = MagicMock()
    command = AuthorizedTaskCommands(session, authorization=MagicMock(), audit=MagicMock(),
                                    actor_profile_id=new_record_id(), contexts=MagicMock())
    for value in (None, {}, "bad"):
        with pytest.raises(TaskValidationError):
            await command.audit_evidence(value)
    session.begin.assert_not_called()


async def test_nonhuman_admission(monkeypatch):
    from types import SimpleNamespace
    from httpx import ASGITransport, AsyncClient
    from app.api.deps.auth import get_auth_verification_result
    from app.api.deps.authorization import enforce_authorization_read_rate_limit, get_task_commands
    from app.core.config import Settings
    for kind in ("service", "agent", "space"):
        app = create_app(Settings(environment="test"))
        reached = []
        async def rate():
            reached.append("rate")
        async def verified():
            return SimpleNamespace(token=SimpleNamespace(subject_kind=kind))
        async def forbidden():
            raise AssertionError("nonhuman reached TASK composition")
        app.dependency_overrides[enforce_authorization_read_rate_limit] = rate
        app.dependency_overrides[get_auth_verification_result] = verified
        app.dependency_overrides[get_task_commands] = forbidden
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
            response = await client.get(path(new_record_id(), new_record_id()))
        assert response.status_code == 404 and reached == ["rate"]
