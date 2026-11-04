"""Late setup projection recovery preserves exact finalization and live authority."""

import pytest
from sqlalchemy import text

from tests.committed_guide_fixtures import create_committed_document_fixture
from tests.projects.client_fixtures import (
    project_client as project_client,
    project_database_env as project_database_env,
)
from .test_automatic_request import automatic_source as automatic_source
from .live_fixtures import _delivery, scripted_document_port as scripted_document_port
from .runtime_fixtures import (
    ScriptedGuideRuntime,
    scripted_model_profile as scripted_model_profile,
    scripted_runtime_configuration,
)


@pytest.mark.usefixtures("scripted_model_profile")
@pytest.mark.parametrize(
    "failure", [None, "storage_unavailable", "service_authority_denied", "revoked"]
)
async def test_finalization_between_projections_replays_only_with_current_authority(
    automatic_source, monkeypatch, failure
):
    """A late policy projection reuses only the exact, freshly authorized finalizer."""
    import asyncio
    from app.core.config import get_settings
    from app.modules.projects.api import ProjectGuideSetupFinalizationError
    from app.modules.projects.api.guide_compilation_projections import ProjectGuideProjectionError
    from app.workers import project_setup as worker

    monkeypatch.setenv("WORKSTREAM_CELERY_TASK_ALWAYS_EAGER", "true")
    get_settings.cache_clear()
    factory, actor, setup_id, snapshot = automatic_source
    await create_committed_document_fixture(snapshot["id"])
    delivery = await _delivery(factory, setup_id)
    runtime = ScriptedGuideRuntime()
    monkeypatch.setattr(worker, "create_project_guide_runtime", lambda configuration: runtime)
    monkeypatch.setattr(worker, "project_guide_runtime_configuration", scripted_runtime_configuration)
    primary, duplicate = await worker._coordinator(factory), await worker._coordinator(factory)
    finalize_entered, finalize_release = asyncio.Event(), asyncio.Event()
    policy_entered, policy_release = asyncio.Event(), asyncio.Event()
    primary_finalize = primary._finalize
    duplicate_finalize = duplicate._finalize
    project_policy = duplicate._projections.project_submission_artifact_policy
    replay_calls = 0

    async def held_finalization(command):
        finalize_entered.set()
        await finalize_release.wait()
        return await primary_finalize(command)

    async def held_policy(command):
        policy_entered.set()
        await policy_release.wait()
        if failure in {"storage_unavailable", "service_authority_denied"}:
            raise ProjectGuideProjectionError(failure)
        return await project_policy(command)

    async def fresh_finalization(command):
        nonlocal replay_calls
        replay_calls += 1
        if failure == "revoked":
            async with factory() as session, session.begin():
                await session.execute(
                    text("update actor_identity_links set status='revoked',revoked_at=now(),"
                         "revoked_by='test',revoked_reason='late replay' where id=:id"),
                    {"id": str(actor.identity_link_id)},
                )
        return await duplicate_finalize(command)

    monkeypatch.setattr(primary, "_finalize", held_finalization)
    monkeypatch.setattr(duplicate, "_finalize", fresh_finalization)
    monkeypatch.setattr(duplicate._projections, "project_submission_artifact_policy", held_policy)
    tasks = [asyncio.create_task(primary.run(delivery))]
    try:
        await asyncio.wait_for(finalize_entered.wait(), timeout=30)
        tasks.append(asyncio.create_task(duplicate.run(delivery)))
        await asyncio.wait_for(policy_entered.wait(), timeout=30)
        finalize_release.set()
        receipt = await asyncio.wait_for(tasks[0], timeout=30)
        policy_release.set()
        if failure is None:
            assert await asyncio.wait_for(tasks[1], timeout=30) == receipt
        else:
            error_type = (
                ProjectGuideSetupFinalizationError if failure == "revoked"
                else ProjectGuideProjectionError
            )
            with pytest.raises(error_type) as error:
                await asyncio.wait_for(tasks[1], timeout=30)
            assert error.value.code == (
                "service_authority_denied" if failure == "revoked" else failure
            )
        assert replay_calls == (1 if failure in {None, "revoked"} else 0)
    finally:
        finalize_release.set()
        policy_release.set()
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
    assert runtime.calls == 1
    async with factory() as session:
        assert await session.scalar(text("select count(*) from project_guide_compilations")) == 1
        assert await session.scalar(text("select count(*) from project_guide_setup_finalizations")) == 1


@pytest.mark.usefixtures("scripted_model_profile")
async def test_projection_source_error_without_finalization_is_not_recovered(
    automatic_source, monkeypatch
):
    """A source error cannot create a finalization or conceal missing projections."""
    from app.core.config import get_settings
    from app.modules.projects.api.guide_compilation_projections import ProjectGuideProjectionError
    from app.workers import project_setup as worker

    monkeypatch.setenv("WORKSTREAM_CELERY_TASK_ALWAYS_EAGER", "true")
    get_settings.cache_clear()
    factory, _actor, setup_id, snapshot = automatic_source
    await create_committed_document_fixture(snapshot["id"])
    delivery = await _delivery(factory, setup_id)
    runtime = ScriptedGuideRuntime()
    monkeypatch.setattr(worker, "create_project_guide_runtime", lambda configuration: runtime)
    monkeypatch.setattr(worker, "project_guide_runtime_configuration", scripted_runtime_configuration)
    coordinator = await worker._coordinator(factory)

    async def source_unavailable(command):
        raise ProjectGuideProjectionError("source_state_unavailable")

    async def unexpected_finalization(command):
        pytest.fail("source failure without retained finalization reached the finalizer")

    monkeypatch.setattr(coordinator._projections, "project_guide_sufficiency", source_unavailable)
    monkeypatch.setattr(coordinator, "_finalize", unexpected_finalization)
    with pytest.raises(ProjectGuideProjectionError) as error:
        await coordinator.run(delivery)
    assert error.value.code == "source_state_unavailable"
    assert runtime.calls == 1
    async with factory() as session:
        assert await session.scalar(text("select count(*) from project_guide_compilations")) == 1
        assert await session.scalar(text("select count(*) from project_guide_setup_finalizations")) == 0


