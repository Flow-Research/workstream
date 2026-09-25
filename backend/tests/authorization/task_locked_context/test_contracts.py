"""Exact read contracts, command-field rejection and early input boundaries."""

from unittest.mock import MagicMock

import pytest

from app.core.identifiers import new_record_id
from app.main import create_app
from app.modules.authorization.catalogue import ActionId
from app.modules.authorization.domain.task_authority import TaskAuthorityResourceContext, task_resource_guard
from app.modules.tasks.authorized_commands import AuthorizedTaskCommands
from app.modules.tasks.service import TaskService, TaskValidationError
from tests.authorization.task_locked_context.support import KINDS, path
from tests.tasks.test_locked_context import REFERENCE_FIELDS, SUMMARY


@pytest.mark.parametrize("kind", KINDS)
def test_locked_context_public_contract(kind):
    schema = create_app().openapi()
    assert "/api/v1/tasks/{task_id}/locked-context" not in schema["paths"]
    operation = schema["paths"][path(kind, "{project_id}", "{task_id}")]["get"]
    assert operation["x-workstream-action-id"] == KINDS[kind][1]
    name = KINDS[kind][3] + "TaskLockedContext"
    assert operation["responses"]["200"]["content"]["application/json"]["schema"] == {"$ref":f"#/components/schemas/{name}"}
    assert set(schema["components"]["schemas"][name]["properties"]) == REFERENCE_FIELDS | ({SUMMARY} if kind == "management" else set())
    for method in ("get_task_locked_context", "read_management_task_locked_context", "read_operational_task_locked_context", "read_audit_task_locked_context"):
        assert not hasattr(TaskService, method)


@pytest.mark.parametrize("kind", KINDS)
def test_locked_context_read_rejects_command_fields(kind):
    resource = TaskAuthorityResourceContext(resource_id=new_record_id(), scope_project_id=new_record_id(),
        actor_profile_id=new_record_id(), identity_link_id=new_record_id(), task_status="review_pending",
        assigned_to=None, assignment_id=None, assignment_contributor_id=None,
        locked_context_hash="sha256:" + "a"*64, reason=None)
    action = ActionId(KINDS[kind][1])
    assert task_resource_guard(action, resource)
    for field, value in (("idempotency_key",new_record_id()),("replay_assignment_id",new_record_id()),
                         ("request_digest","sha256:"+"b"*64),("replay_command_id",new_record_id())):
        assert not task_resource_guard(action, resource.model_copy(update={field:value})), field


@pytest.mark.parametrize("kind", KINDS)
async def test_locked_context_invalid_selectors_before_transaction(kind):
    session = MagicMock()
    command = AuthorizedTaskCommands(session, authorization=MagicMock(), audit=MagicMock(),
        actor_profile_id=new_record_id(), contexts=MagicMock())
    for invalid in (None, "bad", str(new_record_id()), 1, True):
        for project, task in ((invalid,new_record_id()),(new_record_id(),invalid)):
            with pytest.raises(TaskValidationError, match="selectors are invalid"):
                await getattr(command, kind + "_locked_context")(project, task)
    session.begin.assert_not_called()


@pytest.mark.parametrize("kind", KINDS)
async def test_locked_context_nonhuman_rejected_before_commands(monkeypatch, kind):
    from types import SimpleNamespace
    from httpx import ASGITransport, AsyncClient
    from app.api.deps.auth import get_auth_verification_result
    from app.api.deps.authorization import enforce_authorization_read_rate_limit, get_task_commands
    from app.core.config import Settings
    from app.modules.tasks.repository import TaskRepository
    for subject_kind in ("service", "agent", "space"):
        app = create_app(Settings(environment="test"))
        reached = []
        async def rate():
            reached.append("rate")
        async def verified():
            return SimpleNamespace(token=SimpleNamespace(subject_kind=subject_kind))
        async def forbidden(*args, **kwargs):
            reached.append("product")
            raise AssertionError("nonhuman reached product")
        app.dependency_overrides[enforce_authorization_read_rate_limit] = rate
        app.dependency_overrides[get_auth_verification_result] = verified
        app.dependency_overrides[get_task_commands] = forbidden
        monkeypatch.setattr(TaskRepository, "lock_project_task", forbidden)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
            response = await client.get(path(kind,new_record_id(),new_record_id()))
        assert reached == ["rate"]
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "project_authorization_resource_not_found"


@pytest.mark.parametrize("kind", KINDS)
async def test_locked_context_dispatch_keeps_exact_role_and_scope(monkeypatch, kind):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock
    from app.modules.authorization import artifact_project_authority as owner
    from app.modules.authorization.schemas import AdminRole
    action = SimpleNamespace(action_id=ActionId(KINDS[kind][1]), permission_id="test-permission")
    locked = AsyncMock(return_value=("actor", "grant"))
    monkeypatch.setattr(owner, "lock_project_admin_authority", locked)
    inputs = [object() for _ in range(4)]
    assert await owner.lock_project_authority(*inputs[:3], action, inputs[3]) == ("actor", "grant")
    assert locked.await_args.kwargs == {
        "system_scope_only": kind == "operational",
        "allowed_roles": frozenset({AdminRole(KINDS[kind][2])}),
    }


@pytest.mark.parametrize("kind", KINDS)
def test_command_guard_probe_detects_omitted_action(monkeypatch, kind):
    from app.modules.authorization.domain import task_authority as owner
    monkeypatch.setattr(owner, "TASK_CONCEALED_READ_ACTIONS", owner.TASK_CONCEALED_READ_ACTIONS - {ActionId(KINDS[kind][1])})
    with pytest.raises(AssertionError, match="idempotency_key"):
        test_locked_context_read_rejects_command_fields(kind)
