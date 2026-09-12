"""A manager correction enters the sole worker with real custody and one model call."""

from uuid import uuid4

import pytest
from sqlalchemy import text

from app.modules.projects.api.guide_compilation import ProjectGuideCompilationDelivery
from app.modules.projects.api.setup_identity import project_guide_compilation_task_id
from tests.projects.guide_compilation.helpers import runtime_configuration
from tests.projects.guide_compilation.runtime_fixtures import ScriptedGuideRuntime, document_access
from .pg_support import proposal_case
from .public_support import proposal_client, proposal_path


@pytest.mark.parametrize("broker_failure", [False, True])
async def test_manual_dispatch_retains_one_human_request_and_one_execution(
    clean_postgres_database, monkeypatch, broker_failure,
):
    from app.core.config import get_settings
    from app.core import project_agents
    from app.modules.projects import setup_queue
    from app.workers import project_setup as worker

    monkeypatch.setenv("WORKSTREAM_CELERY_BROKER_URL", "memory://")
    monkeypatch.setenv("WORKSTREAM_CELERY_RESULT_BACKEND", "cache+memory://")
    get_settings.cache_clear()
    monkeypatch.setattr(project_agents, "project_guide_runtime_configuration", lambda settings: runtime_configuration())
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
    async with proposal_case(clean_postgres_database) as (_, factory, command, actor, _):
        path = proposal_path(command)
        async with proposal_client(factory, actor) as client:
            package = await client.get(path+"/proposal")
            assert package.status_code == 200, package.text
            correction = await client.post(path+"/corrections", headers={"Idempotency-Key":str(uuid4())}, json={
                "target":package.json()["target"], "reason":"Reconsider the requirement using the guide evidence.",
            })
            assert correction.status_code == 201, correction.text
            assert published == [] and runtime.calls == 0
            operation = correction.json()["operation_id"]
            endpoint = path+f"/corrections/{operation}/dispatch"
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
                    "SELECT request_trigger,setup_run_id,setup_generation,source_snapshot_id "
                    "FROM project_guide_compilation_request_operations WHERE expected_predecessor_compilation_id=:id"
                ), {"id":command.compilation_id})).one()
                assert row.request_trigger == "project_manager"
            delivery = ProjectGuideCompilationDelivery(
                project_id=command.project_id, guide_id=command.guide_id,
                source_snapshot_id=row.source_snapshot_id, setup_run_id=row.setup_run_id,
                setup_generation=row.setup_generation,
                task_id=project_guide_compilation_task_id(row.setup_run_id,row.setup_generation),
            )
            coordinator = worker._coordinator(factory)
            async def forbidden_automatic(*args):
                pytest.fail("manual delivery invoked automatic request authority")
            coordinator._request_authority = forbidden_automatic
            result = await coordinator.run(delivery)
            assert result["status"] == "policy_draft_ready", result
            assert runtime.calls == 1
            assert await coordinator.run(delivery) == result
            assert runtime.calls == 1
