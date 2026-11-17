"""The authorized manager reads policy selectors and activates their exact lineage."""

from uuid import uuid4

from sqlalchemy import text

from tests.projects.guide_compilation.proposals.pg_support import revoke_review_grant
from .support import activation_case


async def test_public_activation_replay_after_retirement_and_revocation(isolated_database_env, monkeypatch, post_policy_worker):
    async with activation_case(isolated_database_env, monkeypatch, post_policy_worker) as (
        factory, command, actor, grant, manager, finance, policy_path, path, body, published, version_path,
    ):
        assert body['contribution_policy_version_id'] == published['contribution_policy_version_id']
        current = await manager.get(f"/api/v1/projects/{command.project_id}/contribution-policies/current")
        assert current.status_code == 200, current.text
        assert current.json()["current_published_version_id"] == published["contribution_policy_version_id"]
        key = str(uuid4())
        response = await manager.post(path, json=body, headers={"Idempotency-Key": key})
        assert response.status_code == 200, response.text
        receipt = response.json()
        assert receipt['command'] == body | {'idempotency_key': key}
        assert receipt['contribution']['contribution_policy_version_id'] == body['contribution_policy_version_id']
        async with factory() as session:
            assert await session.scalar(text("select status from projects where id=:id"), {'id': str(command.project_id)}) == 'active'
            stored_operation = await session.scalar(text("select activation_operation_id from project_guides where id=:id"), {'id': str(command.guide_id)})
            assert str(stored_operation) == receipt['operation_id']
        retired = await finance.post(version_path + "/retirement", json={}, headers={"Idempotency-Key": str(uuid4())})
        assert retired.status_code == 200, retired.text
        replay = await manager.post(path, json=body, headers={"Idempotency-Key": key})
        assert replay.status_code == 200 and replay.json() == receipt, replay.text
        await revoke_review_grant(factory, actor, grant)
        for attempt_key in (key, str(uuid4())):
            denied = await manager.post(path, json=body, headers={"Idempotency-Key": attempt_key})
            assert denied.status_code == 404, denied.text
        async with factory() as session:
            assert await session.scalar(text("select count(*) from guide_mutation_idempotency_records where action_id='project.guide.activate'")) == 1
            assert await session.scalar(text("select count(*) from audit_events where action_id='project.guide.activate' and event_type='SensitiveAuthorizationAllowed'")) == 1
