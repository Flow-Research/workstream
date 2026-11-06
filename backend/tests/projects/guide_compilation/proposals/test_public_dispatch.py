"""A manager correction enters the sole worker with real custody and one model call."""

from uuid import uuid4

import pytest
from sqlalchemy import text

from app.core.identifiers import new_record_id
from app.modules.projects.api.guide_compilation import ProjectGuideCompilationDelivery
from app.modules.projects.api.setup_identity import project_guide_compilation_task_id
from tests.projects.client_fixtures import project_database_env as project_database_env
from tests.projects.guide_compilation.runtime_fixtures import (
    ScriptedGuideRuntime,
    configure_scripted_model_transport,
    publish_scripted_model_profile,
    scripted_document_access_runtime,
    scripted_guide_document_parser_factory,
    scripted_runtime_configuration,
)
from .pg_support import proposal_case, seed_review_actor, revoke_review_grant
from .public_support import proposal_client, proposal_path


async def assert_other_actors_cannot_recover(factory, creator, latest_path, endpoint):
    """Neither the revoked creator nor a foreign project's manager can recover this correction."""
    from project_create_fixtures import seed_historical_project
    foreign_project = new_record_id()
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


async def retained_runtime_configuration(factory, setup_id):
    """Read the exact immutable runtime selected by this correction attempt."""
    async with factory() as session:
        return await session.scalar(text(
            "SELECT runtime_configuration FROM project_guide_compilation_attempts "
            "WHERE setup_run_id=:id"
        ), {"id": setup_id})


async def assert_dispatch_keeps_selected_profile(
    factory, actor, project_id, setup_id, configuration, profile,
):
    """A later Operator profile cannot rewrite the committed correction attempt."""
    saved = await retained_runtime_configuration(factory, setup_id)
    assert saved["model_profile_id"] == profile["profile_id"]
    assert saved["model_profile_version"] == profile["spec"]["profile_version"]
    assert saved["model_profile_digest"] == profile["profile_digest"]
    async with proposal_client(factory, actor) as operator:
        newer = await publish_scripted_model_profile(operator, project_id, configuration, version=2)
    assert newer["profile_id"] != profile["profile_id"]


async def replay_without_latest_profile_read(monkeypatch, client, endpoint):
    """An admitted correction reuses its attempt without mutable profile selection."""
    from app.modules.model_usage.profiles import ModelProfileReader

    async def forbidden_latest_profile_read(*_args, **_kwargs):
        pytest.fail("correction replay consulted the latest model profile")

    with monkeypatch.context() as replay_guard:
        replay_guard.setattr(
            ModelProfileReader, "read_latest_matching", forbidden_latest_profile_read
        )
        return await client.post(endpoint)


def configure_manual_dispatch(monkeypatch, tmp_path, broker_failure):
    """Wire the scripted worker and a broker with observable delivery attempts."""
    from app.core.config import get_settings
    from app.core import project_agents
    from app.modules.projects import setup_queue

    monkeypatch.setenv("WORKSTREAM_CELERY_BROKER_URL", "memory://")
    monkeypatch.setenv("WORKSTREAM_CELERY_RESULT_BACKEND_URL", "cache+memory://")
    configure_scripted_model_transport(monkeypatch, tmp_path / "unused-model-proxy.sock")
    get_settings.cache_clear()
    from app.workers import project_setup as worker
    monkeypatch.setattr(project_agents, "project_guide_runtime_configuration", scripted_runtime_configuration)
    monkeypatch.setattr(worker, "guide_document_access_runtime", scripted_document_access_runtime)
    monkeypatch.setattr(
        worker, "guide_document_parser_factory", scripted_guide_document_parser_factory
    )
    runtime = ScriptedGuideRuntime()
    monkeypatch.setattr(worker, "create_project_guide_runtime", lambda configuration:runtime)
    published = []
    def enqueue(**values):
        published.append(values)
        if broker_failure and len(published) == 1:
            raise setup_queue.ProjectSetupQueueError("broker unavailable")
        return values["task_id"]
    monkeypatch.setattr(setup_queue, "enqueue_project_guide_compilation", enqueue)
    return worker, runtime, published


@pytest.mark.parametrize("broker_failure", [False, True])
@pytest.mark.parametrize("manager_handoff", [False, True])
async def test_manual_dispatch_retains_one_human_request_and_one_execution(
    project_database_env, monkeypatch, tmp_path, broker_failure, manager_handoff,  # noqa: F811
):
    from app.core.config import get_settings

    worker, runtime, published = configure_manual_dispatch(
        monkeypatch, tmp_path, broker_failure
    )
    async with proposal_case(project_database_env) as (_, factory, command, actor, grant):
        operator, _ = await seed_review_actor(factory, None, role="operator", scope="system")
        path = proposal_path(command)
        latest_path = f"/api/v1/projects/{command.project_id}/guides/{command.guide_id}/setup-runs/latest"
        async def predecessor_record():
            async with factory() as session:
                return await session.scalar(text(
                    "SELECT row_to_json(f) FROM project_guide_setup_finalizations f WHERE compilation_id=:id"
                ), {"id": command.compilation_id})
        original_finalization = await predecessor_record()
        configuration = scripted_runtime_configuration(
            get_settings(), adapter_profile_builder=lambda value: value
        )
        async with proposal_client(factory, operator) as operator_client:
            profile = await publish_scripted_model_profile(
                operator_client, command.project_id, configuration
            )
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
            await assert_dispatch_keeps_selected_profile(
                factory, operator, command.project_id, pending["id"], configuration, profile,
            )
            replay = await replay_without_latest_profile_read(
                monkeypatch, client, endpoint
            )
            assert replay.status_code == 202, replay.text
            assert len(published) == (2 if broker_failure else 1)
            async with factory() as session:
                row = (await session.execute(text(
                    "SELECT request_trigger,setup_run_id,setup_generation,source_snapshot_id,actor_profile_id "
                    "FROM project_guide_compilation_request_operations WHERE expected_predecessor_compilation_id=:id"
                ), {"id":command.compilation_id})).one()
                assert row.request_trigger == "project_manager"
                assert row.actor_profile_id == current_actor.actor_profile_id
                retained = (await session.execute(text(
                    "SELECT operation_id,actor_profile_id FROM project_guide_proposal_corrections WHERE compilation_id=:id"
                ), {"id": command.compilation_id})).one()
                assert str(retained.operation_id) == operation
                assert retained.actor_profile_id == actor.actor_profile_id
            payload = published[-1]
            assert payload == {
                "project_id": str(command.project_id), "guide_id": str(command.guide_id),
                "source_snapshot_id": str(row.source_snapshot_id),
                "setup_run_id": str(row.setup_run_id),
                "setup_generation": row.setup_generation,
                "task_id": project_guide_compilation_task_id(row.setup_run_id, row.setup_generation),
            }
            async def deliver():
                return await worker._run_project_guide_compilation(
                    ProjectGuideCompilationDelivery(**payload)
                )

            result = await deliver()
            assert result["status"] == "policy_draft_ready", result
            assert runtime.calls == 1
            assert await deliver() == result
            assert runtime.calls == 1
            completed = await client.get(latest_path)
            assert completed.status_code == 200, completed.text
            assert completed.json()["finalized_compilation_id"] is not None
            assert completed.json()["correction_operation_id"] == operation
            assert completed.json()["predecessor_compilation_id"] == predecessor
            assert await predecessor_record() == original_finalization
            saved = await retained_runtime_configuration(factory, pending["id"])
            assert saved["model_profile_id"] == profile["profile_id"]


async def test_manual_dispatch_without_matching_profile_has_no_effects(
    project_database_env, monkeypatch, tmp_path,  # noqa: F811
):
    """A missing Operator profile is concealed before request or queue effects."""
    _worker, runtime, published = configure_manual_dispatch(monkeypatch, tmp_path, False)
    async with proposal_case(project_database_env) as (_, factory, command, actor, _grant):
        path = proposal_path(command)
        async with factory() as session:
            profile_count = await session.scalar(text(
                "SELECT count(*) FROM model_usage_profiles WHERE project_id=:project"
            ), {"project": command.project_id})
        assert profile_count == 0

        async with proposal_client(factory, actor) as client:
            package = await client.get(path + "/proposal")
            assert package.status_code == 200, package.text
            correction = await client.post(
                path + "/corrections",
                headers={"Idempotency-Key": str(uuid4())},
                json={
                    "target": package.json()["target"],
                    "reason": "Reconsider the requirement using the guide evidence.",
                },
            )
            assert correction.status_code == 201, correction.text
            receipt = correction.json()
            endpoint = (
                f"{path}/corrections/{receipt['operation_id']}/dispatch"
            )
            response = await client.post(endpoint)
            assert response.status_code == 404, response.text
            assert response.json()["error"]["code"] == "proposal_unavailable"

        assert published == [] and runtime.calls == 0
        async with factory() as session:
            state = (await session.execute(text(
                "SELECT s.status,s.current_step,s.celery_task_id,"
                "(SELECT count(*) FROM project_guide_compilation_attempts a "
                "WHERE a.setup_run_id=s.id) AS attempts,"
                "(SELECT count(*) FROM project_guide_compilation_request_operations r "
                "WHERE r.setup_run_id=s.id) AS requests "
                "FROM project_setup_runs s WHERE s.id=:setup"
            ), {"setup": receipt["successor_setup_run_id"]})).one()
        assert tuple(state) == ("correction_requested", "correction_requested", None, 0, 0)
