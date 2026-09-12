"""A manager correction enters the sole worker with real custody and one model call."""

from uuid import uuid4

import pytest
from sqlalchemy import text

from app.modules.projects.api.setup_identity import project_guide_compilation_task_id
from tests.projects.guide_compilation.helpers import runtime_configuration
from tests.projects.guide_compilation.runtime_fixtures import ScriptedGuideRuntime, document_access
from .pg_support import proposal_case, seed_review_actor, revoke_review_grant
from .public_support import proposal_client, proposal_path


async def assert_other_actors_cannot_recover(factory, creator, latest_path, endpoint):
    """Neither the revoked creator nor a foreign project's manager can recover this correction."""
    from project_create_fixtures import seed_historical_project
    foreign_project = str(uuid4())
    async with factory() as session, session.begin():
        await seed_historical_project(session, project_id=foreign_project,
                                      name="Other guide owner", slug=f"foreign-{foreign_project}")
    foreign, _ = await seed_review_actor(factory, foreign_project)
    for denied_actor in (creator, foreign):
        async with proposal_client(factory, denied_actor) as denied:
            status = await denied.get(latest_path)
            assert status.status_code == 404, status.text
            assert "correction_operation_id" not in status.text
            rejected = await denied.post(endpoint)
            assert rejected.status_code == 404, rejected.text


@pytest.mark.parametrize("broker_failure", [False, True])
@pytest.mark.parametrize("manager_handoff", [False, True])
async def test_manual_dispatch_retains_one_human_request_and_one_execution(
    isolated_database_env, monkeypatch, broker_failure, manager_handoff,
):
    from app.core.config import get_settings
    from app.core import project_agents
    from app.modules.projects import setup_queue

    monkeypatch.setenv("WORKSTREAM_CELERY_BROKER_URL", "memory://")
    monkeypatch.setenv("WORKSTREAM_CELERY_RESULT_BACKEND_URL", "cache+memory://")
    get_settings.cache_clear()
    from app.workers import project_setup as worker
    monkeypatch.setattr(project_agents, "project_guide_runtime_configuration", lambda settings: runtime_configuration())
    monkeypatch.setattr(worker, "project_guide_runtime_configuration", lambda settings: runtime_configuration())
    monkeypatch.setattr(worker, "guide_document_access_runtime", lambda sessions,*args:document_access(*args))
    runtime = ScriptedGuideRuntime()
    monkeypatch.setattr(worker, "create_project_guide_runtime", lambda configuration:runtime)
    published = []
    def enqueue(**values):
        published.append(values)
        if broker_failure and len(published) == 1:
            raise setup_queue.ProjectSetupQueueError("broker unavailable")
        return values["task_id"]
    monkeypatch.setattr(setup_queue, "enqueue_project_guide_compilation", enqueue)
    async with proposal_case(isolated_database_env) as (_, factory, command, actor, grant):
        path = proposal_path(command)
        latest_path = f"/api/v1/projects/{command.project_id}/guides/{command.guide_id}/setup-runs/latest"
        async def predecessor_record():
            async with factory() as session:
                return await session.scalar(text(
                    "SELECT row_to_json(f) FROM project_guide_setup_finalizations f WHERE compilation_id=:id"
                ), {"id": command.compilation_id})
        original_finalization = await predecessor_record()
        async with proposal_client(factory, actor) as client:
            package = await client.get(path+"/proposal")
            assert package.status_code == 200, package.text
            correction = await client.post(path+"/corrections", headers={"Idempotency-Key":str(uuid4())}, json={
                "target":package.json()["target"], "reason":"Reconsider the requirement using the guide evidence.",
            })
            assert correction.status_code == 201, correction.text
            assert published == [] and runtime.calls == 0
        current_actor = actor
        if manager_handoff:
            # Simulate a lost creation response: no receipt or creator key reaches the next manager.
            del correction, package
            current_actor, _ = await seed_review_actor(factory, command.project_id)
            await revoke_review_grant(factory, actor, grant)
        async with proposal_client(factory, current_actor) as client:
            latest = await client.get(latest_path)
            assert latest.status_code == 200, latest.text
            pending = latest.json()
            assert pending["status"] == "correction_requested"
            assert pending["finalized_compilation_id"] is None
            operation = pending["correction_operation_id"]
            predecessor = pending["predecessor_compilation_id"]
            assert operation is not None and predecessor == str(command.compilation_id)
            if not manager_handoff:
                assert operation == correction.json()["operation_id"]
            endpoint = (
                f"/api/v1/projects/{pending['project_id']}/guides/{pending['guide_id']}"
                f"/compilations/{predecessor}/corrections/{operation}/dispatch"
            )
            if manager_handoff:
                await assert_other_actors_cannot_recover(factory, actor, latest_path, endpoint)
                assert published == [] and runtime.calls == 0
            response = await client.post(endpoint)
            assert response.status_code == 202, response.text
            assert "provider_idempotency_key" not in response.text
            assert len(published) == 1 and runtime.calls == 0
            if broker_failure:
                replay = await client.post(endpoint)
                assert replay.status_code == 202, replay.text
                assert len(published) == 2
            else:
                assert (await client.post(endpoint)).status_code == 202
                assert len(published) == 1
            async with factory() as session:
                row = (await session.execute(text(
                    "SELECT request_trigger,setup_run_id,setup_generation,source_snapshot_id,actor_profile_id "
                    "FROM project_guide_compilation_request_operations WHERE expected_predecessor_compilation_id=:id"
                ), {"id":command.compilation_id})).one()
                assert row.request_trigger == "project_manager"
                assert row.actor_profile_id == str(current_actor.actor_profile_id)
                retained = (await session.execute(text(
                    "SELECT operation_id,actor_profile_id FROM project_guide_proposal_corrections WHERE compilation_id=:id"
                ), {"id": command.compilation_id})).one()
                assert str(retained.operation_id) == operation
                assert retained.actor_profile_id == str(actor.actor_profile_id)
            payload = published[-1]
            assert payload == {
                "project_id": str(command.project_id), "guide_id": str(command.guide_id),
                "source_snapshot_id": row.source_snapshot_id, "setup_run_id": row.setup_run_id,
                "setup_generation": row.setup_generation,
                "task_id": project_guide_compilation_task_id(row.setup_run_id, row.setup_generation),
            }
            def forbidden_automatic(*args):
                pytest.fail("manual delivery invoked automatic request authority")
            monkeypatch.setattr(worker, "guide_compilation_request_authority", forbidden_automatic)
            def deliver():
                return worker.run_project_guide_compilation.apply(
                    args=tuple(payload[key] for key in (
                        "project_id", "guide_id", "source_snapshot_id", "setup_run_id", "setup_generation",
                    )),
                    task_id=payload["task_id"], throw=True,
                ).get()
            result = deliver()
            assert result["status"] == "policy_draft_ready", result
            assert runtime.calls == 1
            assert deliver() == result
            assert runtime.calls == 1
            completed = await client.get(latest_path)
            assert completed.status_code == 200, completed.text
            assert completed.json()["finalized_compilation_id"] is not None
            assert completed.json()["correction_operation_id"] == operation
            assert completed.json()["predecessor_compilation_id"] == predecessor
            assert await predecessor_record() == original_finalization
