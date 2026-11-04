"""Historical locked facts remain readable in every stored lifecycle state."""
import pytest
from sqlalchemy import select

from app.db import session as db_session
from app.modules.authorization.models import AdminRoleGrant
from app.modules.checkers.api.external_policy import validate_stored_external_post_policy
from app.modules.tasks.lifecycle import ALLOWED_TASK_TRANSITIONS
from app.modules.tasks.models import WorkstreamTask
from app.modules.tasks.repository import TaskRepository
from tests.authorization.task_locked_context.support import KINDS, grant_for, path
from tests.authorization.task_reads.support import task_case, create_task
from tests.tasks.test_locked_context import REFERENCE_FIELDS, SUMMARY


@pytest.mark.parametrize("kind", KINDS)
async def test_locked_context_exact_fields_all_states_and_corrupt_custody(admin_access, kind, monkeypatch):
    project, manager, task = await task_case(admin_access)
    await grant_for(admin_access, project, kind)
    factory = db_session.get_session_factory()
    async with factory() as session:
        stored = await session.get(WorkstreamTask, str(task))
        expected = {field: str(getattr(stored, "id" if field == "task_id" else field))
                    if field.endswith("_id") else getattr(stored, field) for field in REFERENCE_FIELDS}
        compiled = validate_stored_external_post_policy(stored.locked_post_submit_checker_policy_body)
        required = [item.registry.capability_id for item in compiled.entries]
        summary = dict(schema_version=compiled.schema_version, default_checkers=[],
                       required_checkers=required, warning_checkers=[],
                       execution_checkers=required, blocking_severities=["critical", "high"])
        expected |= {SUMMARY: summary} if kind == "management" else {}
    states = {state for transition in ALLOWED_TASK_TRANSITIONS for state in transition}
    assert len(states) == 8
    for state in sorted(states):
        # Independent historical rows exercise read visibility without making
        # an invented needs_revision -> ready transition lacking its receipt.
        state_task = await create_task(admin_access, project, manager)
        async with factory() as session, session.begin():
            stored = await session.get(WorkstreamTask, str(state_task))
            stored.status = state
        async with factory() as independent:
            assert (await independent.get(WorkstreamTask, str(state_task))).status == state
        response = await admin_access.signed.client.get(path(kind, project, state_task), headers=admin_access.target.headers)
        assert response.status_code == 200, (state, response.text)
        assert response.json() == {**expected, "task_id": str(state_task)}
    async with factory() as session:
        original_body = dict((await session.get(WorkstreamTask, str(task))).locked_post_submit_checker_policy_body)
    original_lock = TaskRepository.lock_project_task

    async def corrupt_read(repository, project_id, task_id):
        stored = await original_lock(repository, project_id, task_id)
        if stored is not None and stored.id == str(task):
            repository._session.expunge(stored)
            stored.locked_post_submit_checker_policy_body = {**original_body, "policy_sha256": "sha256:" + "0" * 64}
        return stored

    monkeypatch.setattr(TaskRepository, "lock_project_task", corrupt_read)
    response = await admin_access.signed.client.get(path(kind, project, task), headers=admin_access.target.headers)
    assert response.status_code == 422, response.text
    assert response.json()["error"]["code"] == "task_locked_context_invalid"
    async with factory() as independent:
        assert (await independent.get(WorkstreamTask, str(task))).locked_post_submit_checker_policy_body == original_body


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
    with pytest.raises(AssertionError, match="draft") as detected:
        await test_locked_context_exact_fields_all_states_and_corrupt_custody(admin_access, "management", monkeypatch)
    assert "404 == 200" in str(detected.value)
