"""Pending TASK projection uses fresh operation authority and exact associations."""

import pytest
from types import SimpleNamespace
from sqlalchemy import text

from app.adapters.artifacts import PendingSubmissionReader
from app.core.identifiers import new_record_id
from app.modules.tasks.api.pending_submission import PendingSubmissionOperationUnavailable
from tests.artifacts.test_submission_intake_admission import (
    admission_intake as admission_intake, admit_new,
)
from tests.authentication.fixtures import (
    auth_database_env as auth_database_env,
    clear_settings_cache as clear_settings_cache,
    rsa_signing_material as rsa_signing_material,
)
from tests.authorization.admin_access.fixtures import (
    signed_access as signed_access, admin_access as admin_access,
)
from tests.tasks.lineage_fixtures import seed_started_task_for_artifact_test
from tests.artifacts.intake_recovery_support import recovery_intake as recovery_intake


async def remove_fixture_management(f):
    async with f.factory() as session:
        grants = list(await session.scalars(text("""
            SELECT id FROM admin_role_grants WHERE target_actor_profile_id=:actor
              AND role='project_manager' AND status='active'
        """), {"actor": f.actor.actor_profile_id}))
    assert grants
    for grant_id in grants:
        revoked = await f.access.signed.revoke(f.access.admin, str(grant_id))
        assert revoked.status_code == 200, revoked.text


@pytest.mark.parametrize("stage", ["receiving", "pre_checking"])
async def test_task_pending_stage_and_revoked_read_authority(admission_intake, tmp_path, stage):
    f = admission_intake
    await remove_fixture_management(f)
    if stage == "receiving":
        owner = await admit_new(f)
    else:
        from tests.artifacts.intake_acceptance_support import completed_source
        owner, _, _ = await completed_source(f, tmp_path)
    client = f.access.signed.client
    path = f"/api/v1/tasks/{f.task}"
    for suffix in ("", "/work-context"):
        response = await client.get(path + suffix, headers=f.access.target.headers)
        assert response.status_code == 200, response.text
        detail = response.json()["task"] if suffix else response.json()
        assert detail["pending_submission_operation"] == {
            "operation_id": str(owner.operation_id), "processing_stage": stage,
        }
    revoked = await client.post(
        f"/api/v1/projects/{f.project}/role-grants/{f.grant_id}/revoke",
        headers=f.manager.headers | {"Idempotency-Key": str(new_record_id())},
        json={"reason": "Withdraw submission operation read access"},
    )
    assert revoked.status_code == 200, revoked.text
    for suffix in ("", "/work-context"):
        response = await client.get(path + suffix, headers=f.access.target.headers)
        assert response.status_code == 404, response.text
        assert str(owner.operation_id) not in response.text
    async with f.factory() as session:
        assert await session.scalar(text("""
            SELECT count(*) FROM audit_events
            WHERE action_id IN ('task.read','task.work_context.read') AND project_id=:id
              AND after_facts->>'allowed'='false'
        """), {"id": str(f.project)}) == 2
    manager = await client.get(
        f"/api/v1/projects/{f.project}/tasks/{f.task}", headers=f.manager.headers,
    )
    assert manager.status_code == 200, manager.text
    assert manager.json()["pending_submission_operation"]["operation_id"] == str(owner.operation_id)


async def test_pending_reader_rejects_missing_and_cross_task_associations(admission_intake):
    f = admission_intake
    owner = await admit_new(f)
    other_task, other_assignment = new_record_id(), new_record_id()
    async with f.factory.kw["bind"].begin() as connection:
        await seed_started_task_for_artifact_test(connection, {
            "task": str(other_task), "assignment": str(other_assignment),
            "project": str(f.project), "actor": str(f.actor.actor_profile_id),
        })
    other = SimpleNamespace(**(vars(f) | {"task": other_task, "assignment": other_assignment}))
    other_owner = await admit_new(other)
    for task_id, operation_id in ((f.task, owner.operation_id), (other_task, other_owner.operation_id)):
        async with f.factory() as session, session.begin():
            valid = await PendingSubmissionReader(session, f.actor).read(task_id, operation_id)
            assert valid.operation_id == operation_id and valid.processing_stage == "receiving"
    for task_id, operation_id in ((other_task, owner.operation_id), (f.task, other_owner.operation_id), (f.task, new_record_id())):
        async with f.factory() as session, session.begin():
            with pytest.raises(PendingSubmissionOperationUnavailable):
                await PendingSubmissionReader(session, f.actor).read(task_id, operation_id)
    async with f.factory() as session:
        with pytest.raises(PendingSubmissionOperationUnavailable, match="caller transaction"):
            await PendingSubmissionReader(session, f.actor).read(f.task, owner.operation_id)


async def test_active_task_pointer_requires_composed_reader(admission_intake, monkeypatch):
    import app.adapters.tasks as composition
    f = admission_intake
    await admit_new(f)
    original = composition.task_commands

    def without_reader(*args, **kwargs):
        kwargs["pending_submissions"] = None
        return original(*args, **kwargs)

    monkeypatch.setattr(composition, "task_commands", without_reader)
    response = await f.access.signed.client.get(
        f"/api/v1/tasks/{f.task}", headers=f.access.target.headers,
    )
    assert response.status_code == 503, response.text
    assert response.json()["error"]["code"] == "task_authority_unavailable"


async def test_pending_task_stage_uses_actual_stalled_finalization(recovery_intake):
    f, owner = recovery_intake.f, recovery_intake.owner
    for prefix, headers in (("/api/v1", f.access.target.headers),
                            (f"/api/v1/projects/{f.project}", f.manager.headers)):
        for suffix in ("", "/work-context"):
            response = await f.access.signed.client.get(f"{prefix}/tasks/{f.task}{suffix}", headers=headers)
            assert response.status_code == 200, response.text
            detail = response.json()["task"] if suffix else response.json()
            assert detail["pending_submission_operation"] == {
                "operation_id": str(owner.operation_id), "processing_stage": "operationally_stalled",
            }


async def test_reviewer_task_visibility_does_not_disclose_pending_submitter_operation(admission_intake):
    from tests.authorization.task_authority.test_postgresql import grant
    f = admission_intake
    await remove_fixture_management(f)
    await grant(f.access, f.manager, f.project, role="reviewer")
    owner = await admit_new(f)
    client = f.access.signed.client
    path = f"/api/v1/tasks/{f.task}"
    before = await client.get(path, headers=f.access.target.headers)
    assert before.status_code == 200, before.text
    assert before.json()["pending_submission_operation"]["operation_id"] == str(owner.operation_id)
    revoked = await client.post(
        f"/api/v1/projects/{f.project}/role-grants/{f.grant_id}/revoke",
        headers=f.manager.headers | {"Idempotency-Key": str(new_record_id())},
        json={"reason": "Keep reviewer visibility only"},
    )
    assert revoked.status_code == 200, revoked.text
    detail = await client.get(path, headers=f.access.target.headers)
    assert detail.status_code == 200, detail.text
    assert detail.json()["pending_submission_operation"] is None
    assert str(owner.operation_id) not in detail.text
    context = await client.get(path + "/work-context", headers=f.access.target.headers)
    assert context.status_code == 404, context.text
    async with f.factory() as session:
        assert await session.scalar(text("""
            SELECT count(*) FROM audit_events WHERE action_id='task.submission_operation.read'
              AND resource_id=:id AND after_facts->>'allowed'='false'
        """), {"id": str(owner.operation_id)}) == 1
