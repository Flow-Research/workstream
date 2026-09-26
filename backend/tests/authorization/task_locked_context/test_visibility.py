"""Historical locked facts remain readable in every stored lifecycle state."""
import json

import pytest
from sqlalchemy import select

from app.db import session as db_session
from app.modules.authorization.models import AdminRoleGrant
from app.modules.checkers.api.post_submit_catalogue import CompiledPostSubmitPolicy
from app.modules.tasks.lifecycle import ALLOWED_TASK_TRANSITIONS
from app.modules.tasks.models import WorkstreamTask
from tests.authorization.task_locked_context.support import KINDS, grant_for, path
from tests.authorization.task_reads.support import task_case
from tests.tasks.test_locked_context import REFERENCE_FIELDS, SUMMARY, SUMMARY_FIELDS


@pytest.mark.parametrize("kind", KINDS)
async def test_locked_context_exact_fields_all_states_and_corrupt_custody(admin_access, kind):
    project, _, task = await task_case(admin_access)
    await grant_for(admin_access, project, kind)
    factory = db_session.get_session_factory()
    async with factory() as session:
        stored = await session.get(WorkstreamTask, str(task))
        expected = {field: str(getattr(stored, "id" if field == "task_id" else field))
                    if field.endswith("_id") else getattr(stored, field) for field in REFERENCE_FIELDS}
        compiled = CompiledPostSubmitPolicy.model_validate_json(json.dumps(stored.locked_post_submit_checker_policy_body))
        summary = {field: getattr(compiled, field) for field in SUMMARY_FIELDS}
        summary["blocking_severities"] = list(compiled.blocking_severities)
        expected |= {SUMMARY: summary} if kind == "management" else {}
    states = {state for transition in ALLOWED_TASK_TRANSITIONS for state in transition}
    assert len(states) == 9
    for state in sorted(states):
        async with factory() as session, session.begin():
            stored = await session.get(WorkstreamTask, str(task))
            stored.status = state
        async with factory() as independent:
            assert (await independent.get(WorkstreamTask, str(task))).status == state
        response = await admin_access.signed.client.get(path(kind, project, task), headers=admin_access.target.headers)
        assert response.status_code == 200, (state, response.text)
        assert response.json() == expected
    async with factory() as session, session.begin():
        stored = await session.get(WorkstreamTask, str(task))
        stored.locked_post_submit_checker_policy_body = {**stored.locked_post_submit_checker_policy_body, "blocking_severities": []}
    async with factory() as independent:
        assert (await independent.get(WorkstreamTask, str(task))).locked_post_submit_checker_policy_body["blocking_severities"] == []
    response = await admin_access.signed.client.get(path(kind, project, task), headers=admin_access.target.headers)
    assert response.status_code == 422, response.text
    assert response.json()["error"]["code"] == "task_locked_context_invalid"


async def test_task_creator_has_no_context_authority_after_revocation(admin_access):
    project, creator, task = await task_case(admin_access)
    async with db_session.get_session_factory()() as session:
        stored = await session.get(WorkstreamTask, str(task))
        assert stored.created_by == str(creator.id)
        grant = await session.scalar(select(AdminRoleGrant).where(
            AdminRoleGrant.target_actor_profile_id == str(creator.id),
            AdminRoleGrant.role == "project_manager", AdminRoleGrant.status == "active",
        ))
        grant_id = grant.id
    before = await admin_access.signed.client.get(path("management", project, task), headers=creator.headers)
    assert before.status_code == 200, before.text
    revoke = await admin_access.signed.revoke(admin_access.admin, grant_id)
    assert revoke.status_code == 200, revoke.text
    after = await admin_access.signed.client.get(path("management", project, task), headers=creator.headers)
    assert after.status_code == 404, after.text


async def test_state_visibility_probe_detects_restrictive_guard(admin_access, monkeypatch):
    from app.modules.authorization.domain import task_authority as owner
    original = owner.task_resource_guard
    def ready_only(action, resource):
        return original(action, resource) and (action not in owner.TASK_LOCKED_CONTEXT_READ_ACTIONS or resource.task_status == "ready")
    monkeypatch.setattr(owner, "task_resource_guard", ready_only)
    with pytest.raises(AssertionError, match="claimed") as detected:
        await test_locked_context_exact_fields_all_states_and_corrupt_custody(admin_access, "management")
    assert "404 == 200" in str(detected.value)
