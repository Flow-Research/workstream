"""Closed read guards, public schemas and removal of obsolete wrappers."""
from unittest.mock import MagicMock

import pytest

from app.core.identifiers import new_record_id
from app.main import create_app
from app.modules.authorization.catalogue import ACTION_BY_ID, ActionId, ActionAvailability, PermissionId
from app.modules.authorization.domain.task_authority import TaskAuthorityResourceContext, task_resource_guard
from app.modules.tasks.authorized_commands import AuthorizedTaskCommands
from app.modules.tasks.lifecycle import ALLOWED_TASK_TRANSITIONS
from app.modules.tasks.service import TaskService, TaskValidationError
from tests.authorization.task_reads.support import READS


@pytest.mark.parametrize("kind", READS)
def test_task_read_guards(kind):
    action = ActionId(READS[kind][1])
    definition = ACTION_BY_ID[action]
    assert definition.availability is ActionAvailability.ACTIVE
    contributor = kind.startswith("contributor")
    assert definition.permission_id is (PermissionId.TASK_QUEUE_READ if contributor else PermissionId.PROJECT_TASK_MANAGE)
    actor = new_record_id()
    resource = TaskAuthorityResourceContext(resource_id=new_record_id(), scope_project_id=new_record_id(),
        actor_profile_id=actor, identity_link_id=new_record_id(), task_status="ready", assigned_to=None,
        assignment_id=None, assignment_contributor_id=None, locked_context_hash="sha256:" + "a" * 64, reason=None)
    assert task_resource_guard(action, resource)
    states = {state for transition in ALLOWED_TASK_TRANSITIONS for state in transition}
    assert len(states) == 9
    for state in states:
        assert task_resource_guard(action, resource.model_copy(update={"task_status": state})) is (not contributor or state == "ready")
        owned = resource.model_copy(update={"task_status": state, "assignment_id": new_record_id(), "assigned_to": actor, "assignment_contributor_id": actor})
        assert task_resource_guard(action, owned)
    if contributor:
        for changes in ({"assignment_id":None}, {"assigned_to":None}, {"assignment_contributor_id":None},
                        {"assigned_to":new_record_id()}, {"assignment_contributor_id":new_record_id()}):
            assert not task_resource_guard(action, owned.model_copy(update=changes))
    for field,value in (("idempotency_key",new_record_id()),("replay_assignment_id",new_record_id()),
                        ("request_digest","sha256:"+"b"*64),("replay_command_id",new_record_id())):
        assert not task_resource_guard(action, resource.model_copy(update={field:value}))


def test_task_read_public_contract_and_removed_wrappers():
    schema = create_app().openapi()
    for kind,(route,action) in READS.items():
        route=route.replace("{task}","{task_id}").replace("{project}","{project_id}")
        operation=schema["paths"][route]["get"]
        name=("Contributor" if kind.startswith("contributor") else "Management") + ("TaskDetail" if kind.endswith("detail") else "TaskSubmissionRequirements")
        assert operation["x-workstream-action-id"] == action
        assert operation["responses"]["200"]["content"]["application/json"]["schema"] == {"$ref":f"#/components/schemas/{name}"}
        assert "task_id" in schema["components"]["schemas"][name]["properties"]
        assert "id" not in schema["components"]["schemas"][name]["properties"]
    assert not hasattr(TaskService,"get_task")
    assert not hasattr(TaskService,"get_task_submission_requirements")
    # The literal ready path must match before the project detail UUID route.
    routes=list(schema["paths"])
    assert routes.index("/api/v1/projects/{project_id}/tasks/ready") < routes.index("/api/v1/projects/{project_id}/tasks/{task_id}")


@pytest.mark.parametrize("method", READS)
async def test_task_read_invalid_internal_selectors(method):
    session=MagicMock()
    commands=AuthorizedTaskCommands(session,authorization=MagicMock(),audit=MagicMock(),actor_profile_id=new_record_id(),contexts=MagicMock())
    for invalid in (None,"bad",str(new_record_id()),[]):
        args=(new_record_id(),invalid) if method.startswith("management") else (invalid,)
        with pytest.raises(TaskValidationError):
            await getattr(commands,method)(*args)
        if method.startswith("management"):
            with pytest.raises(TaskValidationError):
                await getattr(commands,method)(invalid,new_record_id())
    session.begin.assert_not_called()
