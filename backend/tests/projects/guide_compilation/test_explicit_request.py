"""Explicit PM request custody, public selection, and recovery boundaries."""

import asyncio
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select, text

from app.adapters.artifacts import guide_document_manifest_port
from app.modules.projects.api.guide_documents import GuideDocumentUnavailable
from app.modules.authorization.api import AuthorizationDenied
from app.modules.projects.guide_compilation.request_inputs import CompilationRequestInputs
from app.modules.projects.guide_compilation.repository import GuideCompilationIntegrityError
from app.modules.projects.guide_compilation.models import ProjectGuideCompilationRequestOperation
from app.modules.projects.guide_setup_continuation import retryable_compilation_dispatch_predicate
from app.modules.projects.models import ProjectSetupRun
from tests.committed_guide_fixtures import create_committed_document_fixture
from tests.projects.client_fixtures import (
    project_client as project_client, project_database_env as project_database_env,
)
from .helpers import manager_runtime_configuration, runtime_configuration
from tests.projects.guide_fixtures import create_guide, complete_guide_payload
from .pending_source import pending_source as pending_source, request_pending_source, manager_actor
from .test_authorized_request_service import _authorized_service
from .proposals.public_support import proposal_client
from .runtime_fixtures import scripted_model_profile, scripted_runtime_configuration  # noqa: F401


async def state_counts(factory):
    async with factory() as session:
        return tuple([await session.scalar(text(f"select count(*) from {name}")) for name in (
            "project_guide_compilation_request_operations", "project_guide_compilation_attempts")])


async def revoke_project_manager(factory, actor, project_id):
    async with factory() as session:
        grant = await session.scalar(text("select id from admin_role_grants where target_actor_profile_id=:actor "
            "and role='project_manager' and scope_type='project' and scope_project_id=:project and status='active'"),
            {"actor": str(actor.actor_profile_id), "project": project_id})
    from .proposals.pg_support import revoke_review_grant
    await revoke_review_grant(factory, actor, grant)



async def test_completed_originals_and_recovery_do_not_request_compilation(pending_source):
    factory, _, setup_id, snapshot = pending_source
    await create_committed_document_fixture(snapshot["id"])
    async with factory() as session:
        assert await session.scalar(select(ProjectSetupRun.id).where(
            retryable_compilation_dispatch_predicate())) is None
        setup = await session.get(ProjectSetupRun, str(setup_id))
        assert setup.status == "awaiting_documents"
        from app.modules.projects.guide_compilation.diagnostics import compilation_setup_response
        assert (await compilation_setup_response(session, setup)).status == "not_requested"
    assert await state_counts(factory) == (0, 0)


async def test_initial_request_requires_complete_originals_then_replays_one_exact_attempt(pending_source):
    factory, _, setup_id, snapshot = pending_source
    key = uuid4()
    with pytest.raises(GuideDocumentUnavailable, match="guide_documents_incomplete"):
        await request_pending_source(factory, setup_id, manager_runtime_configuration(), key=key)
    assert await state_counts(factory) == (0, 0)
    await create_committed_document_fixture(snapshot["id"])
    first = await request_pending_source(factory, setup_id, manager_runtime_configuration(), key=key)
    replay = await request_pending_source(factory, setup_id, manager_runtime_configuration(), key=key)
    assert first == replay
    assert await state_counts(factory) == (1, 1)
    async with factory() as session:
        operation = await session.scalar(select(ProjectGuideCompilationRequestOperation))
        assert operation.request_trigger == "project_manager"
        assert operation.source_mutation_operation_id is None
        assert operation.source_authorization_decision_event_id is None
        assert (await session.get(ProjectSetupRun, str(setup_id))).status == "dispatch_pending"


async def test_concurrent_initial_replays_share_one_attempt(pending_source):
    factory, _, setup_id, snapshot = pending_source
    await create_committed_document_fixture(snapshot["id"])
    key = uuid4()
    first, second = await asyncio.gather(*[
        request_pending_source(factory, setup_id, manager_runtime_configuration(), key=key)
        for _ in range(2)])
    assert first == second
    assert await state_counts(factory) == (1, 1)


async def test_replay_requires_current_pm_authority_and_mode_is_bound(pending_source):
    factory, _, setup_id, snapshot = pending_source
    await create_committed_document_fixture(snapshot["id"])
    key = uuid4()
    await request_pending_source(factory, setup_id, manager_runtime_configuration(), key=key)
    actor = await manager_actor(factory, snapshot["project_id"])
    async with factory() as session:
        inputs = CompilationRequestInputs(guide_document_manifest_port(session), runtime_configuration())
        with pytest.raises(GuideCompilationIntegrityError, match="mode mismatch"):
            await _authorized_service(session, actor, request_inputs=inputs).request_initial(
                actor=actor, setup_run_id=setup_id, idempotency_key=key, inference_required=True)
    await revoke_project_manager(factory, actor, snapshot["project_id"])
    async with factory() as session:
        inputs = CompilationRequestInputs(guide_document_manifest_port(session), manager_runtime_configuration())
        with pytest.raises(AuthorizationDenied):
            await _authorized_service(session, actor, request_inputs=inputs).request_initial(
                actor=actor, setup_run_id=setup_id, idempotency_key=key, inference_required=True)
    assert await state_counts(factory) == (1, 1)


async def test_rules_compile_public_command_is_provider_free_and_recovers_broker_failure(pending_source, monkeypatch):
    factory, _, setup_id, snapshot = pending_source
    await create_committed_document_fixture(snapshot["id"])
    actor = await manager_actor(factory, snapshot["project_id"])
    from app.modules.projects import setup_queue
    published = []
    def publish(**kwargs):
        published.append(kwargs)
        if len(published) == 1:
            raise setup_queue.ProjectSetupQueueError("broker unavailable")
        return kwargs["task_id"]
    monkeypatch.setattr(setup_queue, "enqueue_project_guide_compilation", publish)
    path = f'/api/v1/projects/{snapshot["project_id"]}/guides/{snapshot["guide_id"]}'
    key = str(uuid4())
    async with proposal_client(factory, actor) as client:
        first = await client.post(path + "/requirements/compile", headers={"Idempotency-Key": key})
        assert first.status_code == 202, first.text
        assert first.json()["status"] == "enqueue_failed"
        replay = await client.post(path + "/requirements/compile", headers={"Idempotency-Key": key})
        assert replay.status_code == 202, replay.text
        assert replay.json()["status"] == "queued"
        assert replay.json()["operation_id"] == first.json()["operation_id"]
        changed = await client.post(path + "/setup", headers={"Idempotency-Key": key})
        assert changed.status_code == 409, changed.text
        assert len(published) == 2
    async with factory() as session:
        configuration = await session.scalar(text("select runtime_configuration::jsonb from project_guide_compilation_attempts"))
        assert {configuration[name] for name in ("model_provider", "model_api", "model")} == {"none"}
        assert configuration["runtime_key"] == "manager_authored"
    assert await state_counts(factory) == (1, 1)


async def test_missing_explicit_key_fails_before_actor_or_database():
    from httpx import AsyncClient, ASGITransport
    from app.main import create_app
    from app.api.deps.authorization import get_authorization_actor
    async def forbidden():
        pytest.fail("missing key resolved identity")
    app = create_app()
    app.dependency_overrides[get_authorization_actor] = forbidden
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        for suffix in ("setup", "requirements/compile"):
            response = await client.post(f"/api/v1/projects/{uuid4()}/guides/{uuid4()}/{suffix}")
            assert response.status_code == 422


@pytest.mark.asyncio
async def test_reservation_and_public_setup_read_share_parent_lock_order(
    pending_source, project_client, project_database_env, monkeypatch
):
    """An intermediate status read cannot deadlock the attempt's parent FK lock."""
    import asyncio
    from uuid import uuid4

    from app.modules.projects import router
    from app.modules.projects.guide_compilation.repository import GuideCompilationRepository
    from tests.auth_concurrency_support import wait_for_named_database_lock
    from tests.projects.client_fixtures import auth_headers

    factory, actor, setup_id, snapshot = pending_source
    await create_committed_document_fixture(snapshot["id"])
    held, release = asyncio.Event(), asyncio.Event()
    waiter_name = "guide-reservation-read-" + uuid4().hex
    pids = {}
    reserve = GuideCompilationRepository.reserve_attempt
    diagnostic = router.authorize_project_diagnostic_read

    async def paused_reserve(repository, *args, **kwargs):
        pids["reservation"] = await repository._session.scalar(text("select pg_backend_pid()"))
        held.set()
        await release.wait()
        return await reserve(repository, *args, **kwargs)

    async def named_diagnostic(**kwargs):
        session = kwargs["repository"]._session
        pids["read"] = await session.scalar(text("select pg_backend_pid()"))
        await session.execute(
            text("select set_config('application_name', :name, true)"),
            {"name": waiter_name},
        )
        return await diagnostic(**kwargs)

    monkeypatch.setattr(GuideCompilationRepository, "reserve_attempt", paused_reserve)
    monkeypatch.setattr(router, "authorize_project_diagnostic_read", named_diagnostic)

    async def request():
        return await request_pending_source(factory, setup_id, manager_runtime_configuration())

    tasks = [asyncio.create_task(request())]
    try:
        await asyncio.wait_for(held.wait(), timeout=30)
        tasks.append(asyncio.create_task(project_client.get(
            f"/api/v1/projects/{snapshot['project_id']}/guides/{snapshot['guide_id']}/setup-runs/latest",
            headers=auth_headers(),
        )))
        await asyncio.wait_for(wait_for_named_database_lock(
            project_database_env, waiter_name,
            expected_blocker_pid=pids["reservation"],
        ), timeout=15)
        assert pids["read"] != pids["reservation"]
        assert not tasks[1].done()
        release.set()
        receipt, response = await asyncio.wait_for(asyncio.gather(*tasks), timeout=30)
        assert response.status_code == 200, response.text
        assert response.json()["id"] == str(setup_id)
        assert receipt is not None
    finally:
        release.set()
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    async with factory() as session:
        for table in (
            "project_guide_compilation_attempts",
            "project_guide_compilation_request_operations",
        ):
            assert await session.scalar(text(f"select count(*) from {table}")) == 1
        assert await session.scalar(text(
            "select count(*) from audit_events "
            "where action_id='project.guide_compilation.request'"
        )) == 1


@pytest.mark.asyncio
async def test_manager_mutation_and_diagnostic_read_lock_actor_before_project(
    pending_source, project_client, project_database_env, monkeypatch
):
    """A status read cannot hold Project while waiting on the mutating manager."""
    import asyncio
    from uuid import uuid4

    from app.modules.projects import router
    from app.modules.projects.repository import ProjectRepository
    from tests.auth_concurrency_support import wait_for_named_database_lock
    from tests.projects.client_fixtures import auth_headers

    _, _, setup_id, snapshot = pending_source
    held, release = asyncio.Event(), asyncio.Event()
    waiter_name = "guide-manager-read-" + uuid4().hex
    pids = {}
    get_project = ProjectRepository.get_project
    diagnostic = router.authorize_project_diagnostic_read

    async def paused_project(repository, project_id, *, for_update=False):
        if (for_update and asyncio.current_task().get_name() == "manager-mutation"
                and not held.is_set()):
            pids["mutation"] = await repository._session.scalar(text("select pg_backend_pid()"))
            held.set()
            await release.wait()
        return await get_project(repository, project_id, for_update=for_update)

    async def named_diagnostic(**kwargs):
        session = kwargs["repository"]._session
        pids["read"] = await session.scalar(text("select pg_backend_pid()"))
        await session.execute(
            text("select set_config('application_name', :name, true)"),
            {"name": waiter_name},
        )
        return await diagnostic(**kwargs)

    monkeypatch.setattr(ProjectRepository, "get_project", paused_project)
    monkeypatch.setattr(router, "authorize_project_diagnostic_read", named_diagnostic)
    payload = complete_guide_payload()
    payload["version"] = "manager-lock-successor"
    tasks = [asyncio.create_task(
        create_guide(project_client, snapshot["project_id"], payload), name="manager-mutation"
    )]
    try:
        await asyncio.wait_for(held.wait(), timeout=30)
        tasks.append(asyncio.create_task(project_client.get(
            f"/api/v1/projects/{snapshot['project_id']}/guides/{snapshot['guide_id']}/setup-runs/latest",
            headers=auth_headers(),
        )))
        await asyncio.wait_for(wait_for_named_database_lock(
            project_database_env, waiter_name,
            expected_blocker_pid=pids["mutation"],
        ), timeout=15)
        assert pids["read"] != pids["mutation"]
        assert not tasks[1].done()
        release.set()
        guide, response = await asyncio.wait_for(asyncio.gather(*tasks), timeout=30)
        assert guide["id"] != snapshot["guide_id"]
        assert guide["version"] == payload["version"]
        assert response.status_code == 200, response.text
        assert response.json()["id"] == str(setup_id)
    finally:
        release.set()
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


@pytest.mark.parametrize("complete", [False, True])
async def test_unauthorized_and_revoked_initial_commands_conceal_source_and_profile_state(
    pending_source, monkeypatch, complete,
):
    factory, _, _, snapshot = pending_source
    if complete:
        await create_committed_document_fixture(snapshot["id"])
    actor = await manager_actor(factory, snapshot["project_id"])
    from app.core import project_agents
    monkeypatch.setattr(project_agents, "project_guide_runtime_configuration", lambda *args, **kwargs: runtime_configuration())
    path = f'/api/v1/projects/{snapshot["project_id"]}/guides/{snapshot["guide_id"]}'
    foreign = str(UUID(int=7))
    async with proposal_client(factory, actor) as client:
        # The available-profile failure belongs to an authorized PM only.
        unavailable = await client.post(path + "/setup", headers={"Idempotency-Key": str(uuid4())})
        assert unavailable.status_code == 409, unavailable.text
        wrong_project = await client.post(path.replace(snapshot["project_id"], foreign) + "/setup",
                                          headers={"Idempotency-Key": str(uuid4())})
        assert wrong_project.status_code == 404, wrong_project.text
    await revoke_project_manager(factory, actor, snapshot["project_id"])
    async with proposal_client(factory, actor) as client:
        for suffix in ("/setup", "/requirements/compile"):
            response = await client.post(path + suffix, headers={"Idempotency-Key": str(uuid4())})
            assert response.status_code == 404, response.text
    assert await state_counts(factory) == (0, 0)


@pytest.mark.usefixtures("scripted_model_profile")
async def test_public_assistance_reserves_the_selected_inference_profile_without_invoking_it(
    pending_source, monkeypatch,
):
    factory, _, _, snapshot = pending_source
    await create_committed_document_fixture(snapshot["id"])
    actor = await manager_actor(factory, snapshot["project_id"])
    from app.core import project_agents
    from app.modules.projects import setup_queue
    monkeypatch.setattr(project_agents, "project_guide_runtime_configuration", scripted_runtime_configuration)
    published = []
    def publish(**kwargs):
        published.append(kwargs)
        return kwargs["task_id"]
    monkeypatch.setattr(setup_queue, "enqueue_project_guide_compilation", publish)
    async with proposal_client(factory, actor) as client:
        response = await client.post(
            f'/api/v1/projects/{snapshot["project_id"]}/guides/{snapshot["guide_id"]}/setup',
            headers={"Idempotency-Key": str(uuid4())})
        assert response.status_code == 202, response.text
        assert response.json()["status"] == "queued"
    assert len(published) == 1
    async with factory() as session:
        configuration = await session.scalar(text(
            "select runtime_configuration::jsonb from project_guide_compilation_attempts"))
        assert configuration["model_provider"] != "none"
        assert configuration["model_profile_id"] is not None
        assert await session.scalar(text("select count(*) from setup_model_usage_slots")) == 0
    assert await state_counts(factory) == (1, 1)
