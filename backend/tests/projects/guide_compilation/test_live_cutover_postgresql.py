"""Real coordinator/custody with scripted document and model-provider ports."""

from uuid import UUID, uuid4

import pytest
from sqlalchemy import text

from app.modules.projects.api.guide_compilation import ProjectGuideCompilationDeliveryError
from tests.committed_guide_fixtures import create_committed_document_fixture
from tests.projects.client_fixtures import (
    project_client as project_client,
    project_database_env as project_database_env,
)
from .pending_source import pending_source as pending_source, request_pending_source
from .helpers import generated_result, runtime_configuration, manager_runtime_configuration
from .runtime_fixtures import (
    ScriptedGuideRuntime,
    scripted_model_profile as scripted_model_profile,
)


from .live_fixtures import _delivery, scripted_document_port as scripted_document_port


@pytest.mark.parametrize("status", ["draft_ready", "draft_ready_with_warnings", "guide_blocked"])
async def test_pending_exact_delivery_compiles_once_and_replays_finalization(
    pending_source, scripted_model_profile, monkeypatch, status, project_client
):  # noqa: F811
    monkeypatch.setenv("WORKSTREAM_CELERY_TASK_ALWAYS_EAGER", "true")
    from app.core.config import get_settings

    get_settings.cache_clear()
    from app.workers import project_setup as worker

    factory, actor, setup_id, snapshot = pending_source
    await create_committed_document_fixture(snapshot["id"])
    await request_pending_source(factory, setup_id, scripted_model_profile)
    delivery = await _delivery(factory, setup_id)
    runtime = ScriptedGuideRuntime()
    if status != "draft_ready":
        from app.interfaces.project_agents import CompilationFinding

        base_outcome = generated_result()
        runtime.outcome = base_outcome.model_copy(
            update={
                "status": status,
                "findings": (
                    CompilationFinding(
                        severity="blocking_gap" if status == "guide_blocked" else "warning",
                        code="guide.finding",
                        message="Review the guide requirement.",
                    ),
                ),
                "submission_artifact_policy": None
                if status == "guide_blocked"
                else base_outcome.submission_artifact_policy,
                "requirements": () if status == "guide_blocked" else base_outcome.requirements,
            }
        )
    monkeypatch.setattr(worker, "create_project_guide_runtime", lambda configuration: runtime)
    coordinator = await worker._coordinator(factory)
    first = await coordinator.run(delivery)
    assert first["status"] == (
        "sufficiency_blocked" if status == "guide_blocked" else "policy_draft_ready"
    )
    assert runtime.calls == 1
    async with factory() as session:
        before = await session.scalar(text("select count(*) from audit_events"))
        assert (
            await session.scalar(text("select count(*) from project_guide_compilation_attempts"))
            == 1
        )
        assert await session.scalar(
            text("select count(*) from project_guide_component_projection_operations")
        ) == (1 if status == "guide_blocked" else 2)
        assert (
            await session.scalar(text("select count(*) from project_guide_setup_finalizations"))
            == 1
        )
    if status != "guide_blocked":
        from tests.projects.client_fixtures import auth_headers

        async with factory() as session:
            policy_id = await session.scalar(
                text(
                    "select output_submission_artifact_policy_id from project_setup_runs where id=:id"
                ),
                {"id": str(setup_id)},
            )
        response = await project_client.post(
            f"/api/v1/projects/{delivery.project_id}/guides/{delivery.guide_id}/submission-artifact-policies/{policy_id}/approve",
            headers=auth_headers(),
            json={"approval_note": "The removed manual approval route is unavailable."},
        )
        assert response.status_code == 404, response.text
        async with factory() as session:
            for table in [
                "effective_project_submission_artifact_policies",
                "pre_submit_checker_policies",
            ]:
                assert await session.scalar(text("select count(*) from " + table)) == 0

    def forbidden_runtime(_configuration):
        pytest.fail("finalized replay reached request configuration or runtime construction")

    monkeypatch.setattr(worker, "create_project_guide_runtime", forbidden_runtime)
    replay = await (await worker._coordinator(factory)).run(delivery)
    assert replay == first
    assert runtime.calls == 1
    async with factory() as session:
        assert await session.scalar(text("select count(*) from audit_events")) == before
    async with factory() as session, session.begin():
        await session.execute(
            text(
                "update actor_identity_links set status='revoked',revoked_at=now(),"
                "revoked_by='test',revoked_reason='finalized replay probe' where id=:id"
            ),
            {"id": str(actor.identity_link_id)},
        )
    from app.modules.projects.api import ProjectGuideSetupFinalizationError

    with pytest.raises(ProjectGuideSetupFinalizationError) as denied:
        await (await worker._coordinator(factory)).run(delivery)
    assert denied.value.code == "service_authority_denied"
    assert runtime.calls == 1


@pytest.mark.parametrize("phase", ["compilation", "sufficiency", "finalization"])
async def test_compilation_phase_and_public_setup_read_share_parent_lock_order(
    pending_source, scripted_model_profile, project_client, project_database_env, monkeypatch, phase
):
    """A status read during a phase's child INSERT cannot deadlock its parent FK."""
    import asyncio
    from sqlalchemy.ext.asyncio import AsyncSession
    from app.core.config import get_settings
    from app.modules.projects import router
    from app.modules.projects.guide_compilation.models import (
        ProjectGuideCompilation, ProjectGuideSetupFinalization,
    )
    from app.modules.projects.models import GuideSufficiencyReport
    from app.workers import project_setup as worker
    from tests.auth_concurrency_support import wait_for_named_database_lock
    from tests.projects.client_fixtures import auth_headers

    monkeypatch.setenv("WORKSTREAM_CELERY_TASK_ALWAYS_EAGER", "true")
    get_settings.cache_clear()
    factory, _actor, setup_id, snapshot = pending_source
    await create_committed_document_fixture(snapshot["id"])
    await request_pending_source(factory, setup_id, scripted_model_profile)
    delivery = await _delivery(factory, setup_id)
    runtime = ScriptedGuideRuntime()
    monkeypatch.setattr(worker, "create_project_guide_runtime", lambda configuration: runtime)
    coordinator = await worker._coordinator(factory)
    target = {"compilation": ProjectGuideCompilation, "sufficiency": GuideSufficiencyReport,
              "finalization": ProjectGuideSetupFinalization}[phase]
    held, release = asyncio.Event(), asyncio.Event()
    waiter_name, pids = "guide-phase-read-" + uuid4().hex, {}
    flush, diagnostic = AsyncSession.flush, router.authorize_project_diagnostic_read

    async def paused_flush(session, *args, **kwargs):
        if not held.is_set() and any(isinstance(row, target) for row in session.new):
            connection = await session.connection()
            pids["worker"] = await connection.scalar(text("select pg_backend_pid()"))
            held.set()
            await release.wait()
        return await flush(session, *args, **kwargs)

    async def named_diagnostic(**kwargs):
        session = kwargs["repository"]._session
        pids["read"] = await session.scalar(text("select pg_backend_pid()"))
        await session.execute(text("select set_config('application_name', :name, true)"),
                              {"name": waiter_name})
        return await diagnostic(**kwargs)

    monkeypatch.setattr(AsyncSession, "flush", paused_flush)
    monkeypatch.setattr(router, "authorize_project_diagnostic_read", named_diagnostic)
    tasks = [asyncio.create_task(coordinator.run(delivery))]
    try:
        await asyncio.wait_for(held.wait(), timeout=60)
        tasks.append(asyncio.create_task(project_client.get(
            f"/api/v1/projects/{delivery.project_id}/guides/{delivery.guide_id}/setup-runs/latest",
            headers=auth_headers(),
        )))
        await asyncio.wait_for(wait_for_named_database_lock(
            project_database_env, waiter_name, expected_blocker_pid=pids["worker"],
        ), timeout=15)
        assert pids["read"] != pids["worker"]
        assert not tasks[1].done()
        release.set()
        outcome, response = await asyncio.wait_for(asyncio.gather(*tasks), timeout=60)
        assert response.status_code == 200, response.text
        assert response.json()["id"] == str(setup_id)
        assert outcome["status"] == "policy_draft_ready"
        assert runtime.calls == 1
    finally:
        release.set()
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
    async with factory() as session:
        for table, count in (("project_guide_compilations", 1),
                             ("project_guide_component_projection_operations", 2),
                             ("project_guide_setup_finalizations", 1)):
            assert await session.scalar(text(f"select count(*) from {table}")) == count


@pytest.mark.parametrize(
    "field",
    ["project_id", "guide_id", "source_snapshot_id", "setup_run_id", "setup_generation", "task_id"],
)
async def test_stale_delivery_rejects_before_any_compilation_effect(
    pending_source, monkeypatch, field
):
    monkeypatch.setenv("WORKSTREAM_CELERY_TASK_ALWAYS_EAGER", "true")
    from app.core.config import get_settings

    get_settings.cache_clear()
    from app.workers import project_setup as worker

    factory, actor, setup_id, snapshot = pending_source
    await create_committed_document_fixture(snapshot["id"])
    await request_pending_source(factory, setup_id, runtime_configuration())
    delivery = await _delivery(factory, setup_id)

    def forbidden_runtime(_configuration):
        pytest.fail("stale delivery reached configuration or runtime")

    monkeypatch.setattr(worker, "create_project_guide_runtime", forbidden_runtime)
    changed = delivery.model_copy(update={field: 2 if field == "setup_generation" else uuid4()})
    async with factory() as session:
        before = await session.scalar(text("select count(*) from audit_events"))
    with pytest.raises(ProjectGuideCompilationDeliveryError, match="^stale compilation delivery$"):
        await (await worker._coordinator(factory)).run(changed)
    async with factory() as session:
        assert await session.scalar(text("select count(*) from audit_events")) == before
        for table in [
            "project_guide_compilation_request_operations",
            "project_guide_compilation_attempts",
            "project_guide_component_projection_operations",
            "project_guide_setup_finalizations",
        ]:
            assert await session.scalar(text("select count(*) from " + table)) == (1 if table in {"project_guide_compilation_request_operations", "project_guide_compilation_attempts"} else 0)


@pytest.mark.parametrize("outcome", ["invalid", "uncertain"])
async def test_invalid_or_uncertain_attempt_reports_durable_diagnostics_without_projection(
    pending_source, scripted_model_profile, monkeypatch, outcome, project_client
):
    from app.core.config import get_settings
    from app.interfaces.project_agents import (
        ProjectAgentRuntimeError,
        ProjectGuideCompilationInvalidOutputError,
    )
    from app.modules.projects.guide_compilation.diagnostics import compilation_setup_response
    from app.modules.projects.models import ProjectSetupRun

    monkeypatch.setenv("WORKSTREAM_CELERY_TASK_ALWAYS_EAGER", "true")
    get_settings.cache_clear()
    from app.workers import project_setup as worker

    factory, actor, setup_id, snapshot = pending_source
    await create_committed_document_fixture(snapshot["id"])
    await request_pending_source(factory, setup_id, scripted_model_profile)
    delivery = await _delivery(factory, setup_id)
    runtime = ScriptedGuideRuntime()
    runtime.outcome = (
        ProjectGuideCompilationInvalidOutputError("schema_invalid")
        if outcome == "invalid"
        else ProjectAgentRuntimeError("private-provider-detail")
    )
    monkeypatch.setattr(worker, "create_project_guide_runtime", lambda configuration: runtime)
    coordinator = await worker._coordinator(factory)
    # Beat selects the exact delivery before terminal provider custody exists.
    await _select_stale_delivery(factory, delivery)
    first = await coordinator.run(delivery)
    replay = await coordinator.run(delivery)
    assert first == replay
    # The scripted runtime re-enters once for uncertain delivery. Production
    # model custody separately prevents repeating the same paid provider effect.
    assert runtime.calls == (2 if outcome == "uncertain" else 1)
    assert first["status"] == (
        "compilation_invalid_terminal" if outcome == "invalid" else "provider_outcome_unresolved"
    )
    assert first["error_code"] == (
        "schema_invalid" if outcome == "invalid" else None
    )
    if outcome == "invalid":
        assert first["error_summary"] == "Guide compilation returned an invalid result."
    else:
        assert first["error_summary"] is None
    assert (first["finished_at"] is not None) == (outcome == "invalid")
    assert "private-provider-detail" not in str(first)
    from tests.projects.client_fixtures import auth_headers

    path = f"/api/v1/projects/{delivery.project_id}/guides/{delivery.guide_id}/setup-runs/latest"
    async with factory() as session:
        before = await session.scalar(
            text("select to_jsonb(s) from project_setup_runs s where id=:id"), {"id": str(setup_id)}
        )
    denied = await project_client.get(path)
    assert denied.status_code == 401
    response = await project_client.get(path, headers=auth_headers())
    assert response.status_code == 200, response.text
    body = response.json()
    for field in ("status", "error_code", "error_summary"):
        assert body[field] == first[field]
    from datetime import datetime

    assert (datetime.fromisoformat(body["finished_at"]) if body["finished_at"] else None) == (
        datetime.fromisoformat(first["finished_at"]) if first["finished_at"] else None
    )
    assert body["started_at"] is not None
    assert "private-provider-detail" not in response.text
    async with factory() as session:
        assert (
            await session.scalar(
                text("select to_jsonb(s) from project_setup_runs s where id=:id"),
                {"id": str(setup_id)},
            )
            == before
        )
    await _assert_terminal_not_reclaimable(factory, delivery, monkeypatch)
    async with factory() as session:
        setup = await session.get(ProjectSetupRun, str(setup_id))
        assert setup.status == "queued" and setup.current_step == "queued"
        assert setup.output_sufficiency_report_id is None
        diagnostic = await compilation_setup_response(session, setup)
        assert diagnostic.status == first["status"] and diagnostic.error_code == first["error_code"]
        for table in [
            "project_guide_compilations",
            "project_guide_component_projection_operations",
            "project_guide_setup_finalizations",
        ]:
            assert await session.scalar(text("select count(*) from " + table)) == 0


async def test_finalized_receipt_excludes_every_recovery_shape(pending_source, scripted_model_profile, monkeypatch):
    from app.workers import project_setup as worker

    factory, _actor, setup_id, snapshot = pending_source
    await create_committed_document_fixture(snapshot["id"])
    await request_pending_source(factory, setup_id, scripted_model_profile)
    delivery = await _delivery(factory, setup_id)
    runtime = ScriptedGuideRuntime()
    monkeypatch.setattr(worker, "create_project_guide_runtime", lambda configuration: runtime)
    await _select_stale_delivery(factory, delivery)
    receipt = await (await worker._coordinator(factory)).run(delivery)
    assert receipt["status"] == "policy_draft_ready"
    async with factory() as session:
        evidence = await session.scalar(
            text("select to_jsonb(f) from project_guide_setup_finalizations f")
        )
    await _assert_terminal_not_reclaimable(factory, delivery, monkeypatch, finalized=True)
    async with factory() as session:
        assert (
            await session.scalar(
                text("select to_jsonb(f) from project_guide_setup_finalizations f")
            )
            == evidence
        )
    assert runtime.calls == 1


async def _assert_terminal_not_reclaimable(factory, delivery, monkeypatch, *, finalized=False):

    from app.modules.projects import setup_queue

    def forbidden_enqueue(**kwargs):
        pytest.fail("terminal custody was republished after candidate selection")

    monkeypatch.setattr(setup_queue, "enqueue_project_guide_compilation", forbidden_enqueue)
    for status, step, task in (
        ("enqueue_failed", "enqueue", None),
        ("queued", "queued", None),
        ("dispatch_pending", "dispatch", str(delivery.task_id)),
        ("queued", "queued", str(delivery.task_id)),
    ):
        async with factory() as session, session.begin():
            if finalized:
                from scripts.run_isolated_tests import NAME_RE

                assert NAME_RE.fullmatch(await session.scalar(text("select current_database()")))
                # Adversarial queue shapes only; receipt evidence remains untouched.
                # Restore both production guards before exercising real dispatch.
                for trigger in ("finalization_setup_change_guard", "finalization_atomic_custody"):
                    await session.execute(
                        text(f"alter table project_setup_runs disable trigger {trigger}")
                    )
            await session.execute(
                text(
                    "update project_setup_runs set status=:status,current_step=:step,"
                    "celery_task_id=:task,updated_at=now()-interval '2 minutes' where id=:id"
                ),
                {"id": str(delivery.setup_run_id), "status": status, "step": step, "task": task},
            )
            if finalized:
                await session.execute(text("set constraints all immediate"))
                for trigger in ("finalization_setup_change_guard", "finalization_atomic_custody"):
                    await session.execute(
                        text(f"alter table project_setup_runs enable trigger {trigger}")
                    )
        assert delivery.source_snapshot_id not in await _published_continuation_snapshots(factory), (status, task)
        async with factory() as session:
            before = await session.scalar(
                text("select to_jsonb(s) from project_setup_runs s where id=:id"),
                {"id": str(delivery.setup_run_id)},
            )
            returned = await setup_queue.dispatch_project_guide_compilation_after_commit(
                session,
                project_id=str(delivery.project_id),
                guide_id=str(delivery.guide_id),
                source_snapshot_id=str(delivery.source_snapshot_id),
                setup_run_id=str(delivery.setup_run_id),
                setup_generation=delivery.setup_generation,
            )
            assert returned == task
            assert (
                await session.scalar(
                    text("select to_jsonb(s) from project_setup_runs s where id=:id"),
                    {"id": str(delivery.setup_run_id)},
                )
                == before
            )


async def test_publisher_acknowledgement_cannot_overwrite_worker_finalization(
    pending_source, scripted_model_profile, monkeypatch
):
    import asyncio
    import threading
    from app.core.config import get_settings
    from app.modules.projects import setup_queue

    monkeypatch.setenv("WORKSTREAM_CELERY_TASK_ALWAYS_EAGER", "true")
    get_settings.cache_clear()
    from app.workers import project_setup as worker

    factory, actor, setup_id, snapshot = pending_source
    await create_committed_document_fixture(snapshot["id"])
    await request_pending_source(factory, setup_id, scripted_model_profile)
    delivery = await _delivery(factory, setup_id)
    async with factory() as session, session.begin():
        await session.execute(
            text(
                "update project_setup_runs set status='queued',current_step='queued',celery_task_id=null where id=:id"
            ),
            {"id": str(setup_id)},
        )
    published, acknowledge = threading.Event(), threading.Event()

    def publish(**kwargs):
        assert kwargs["task_id"] == str(delivery.task_id)
        published.set()
        assert acknowledge.wait(30), (
            "worker did not reach finalization before publication acknowledgement"
        )
        return kwargs["task_id"]

    monkeypatch.setattr(setup_queue, "enqueue_project_guide_compilation", publish)
    runtime = ScriptedGuideRuntime()
    monkeypatch.setattr(worker, "create_project_guide_runtime", lambda configuration: runtime)

    async def dispatch():
        async with factory() as session:
            return await setup_queue.dispatch_project_guide_compilation_after_commit(
                session,
                project_id=str(delivery.project_id),
                guide_id=str(delivery.guide_id),
                source_snapshot_id=str(delivery.source_snapshot_id),
                setup_run_id=str(setup_id),
                setup_generation=delivery.setup_generation,
            )

    publisher = asyncio.create_task(dispatch())
    try:
        assert await asyncio.to_thread(published.wait, 10)
        receipt = await (await worker._coordinator(factory)).run(delivery)
        assert receipt["status"] == "policy_draft_ready"
        async with factory() as session:
            before = await session.scalar(
                text("select to_jsonb(s) from project_setup_runs s where id=:id"),
                {"id": str(setup_id)},
            )
        acknowledge.set()
        assert await asyncio.wait_for(publisher, 10) == str(delivery.task_id)
        async with factory() as session:
            after = await session.scalar(
                text("select to_jsonb(s) from project_setup_runs s where id=:id"),
                {"id": str(setup_id)},
            )
        assert after == before
        assert runtime.calls == 1
    finally:
        acknowledge.set()
        if not publisher.done():
            publisher.cancel()
        await asyncio.gather(publisher, return_exceptions=True)


@pytest.mark.parametrize(
    "boundary", ["persisted", "sufficiency", "both_projections", "retained_unconfigured"]
)
async def test_phase_crash_recovers_same_attempt_without_reinference(
    pending_source, scripted_model_profile, monkeypatch, boundary
):
    from app.core.config import get_settings

    monkeypatch.setenv("WORKSTREAM_CELERY_TASK_ALWAYS_EAGER", "true")
    get_settings.cache_clear()
    from app.workers import project_setup as worker

    factory, actor, setup_id, snapshot = pending_source
    await create_committed_document_fixture(snapshot["id"])
    await request_pending_source(factory, setup_id, scripted_model_profile)
    delivery = await _delivery(factory, setup_id)
    runtime = ScriptedGuideRuntime()
    monkeypatch.setattr(worker, "create_project_guide_runtime", lambda configuration: runtime)
    coordinator = await worker._coordinator(factory)
    projections = coordinator._projections

    class Crash(Exception):
        pass

    class InterruptedProjections:
        async def project_guide_sufficiency(self, command):
            if boundary in {"persisted", "retained_unconfigured"}:
                raise Crash()
            await projections.project_guide_sufficiency(command)
            if boundary == "sufficiency":
                raise Crash()

        async def project_submission_artifact_policy(self, command):
            await projections.project_submission_artifact_policy(command)
            raise Crash()

    coordinator._projections = InterruptedProjections()
    with pytest.raises(Crash):
        await coordinator.run(delivery)
    if boundary == "retained_unconfigured":
        await _remove_retained_runtime_configuration(factory)

        async with factory() as session, session.begin():
            await session.execute(
                text(
                    "update project_setup_runs set updated_at=now()-interval '2 minutes' where id=:id"
                ),
                {"id": str(setup_id)},
            )
        assert delivery.source_snapshot_id not in await _published_continuation_snapshots(factory)
        from app.modules.projects.guide_compilation.repository import GuideCompilationIntegrityError

        with pytest.raises(
            GuideCompilationIntegrityError, match="compilation runtime configuration unavailable"
        ):
            await coordinator.run(delivery)
        async with factory() as session:
            assert (
                await session.scalar(text("select status from project_guide_compilation_attempts"))
                == "compilation_persisted"
            )
            for table in (
                "project_guide_component_projection_operations",
                "project_guide_setup_finalizations",
            ):
                assert await session.scalar(text("select count(*) from " + table)) == 0
        assert runtime.calls == 1
        return
    coordinator._projections = projections
    await _reclaim_exact_delivery(factory, delivery, monkeypatch)
    receipt = await coordinator.run(delivery)
    assert receipt["status"] == "policy_draft_ready"
    assert runtime.calls == 1
    async with factory() as session:
        assert (
            await session.scalar(text("select count(*) from project_guide_compilation_attempts"))
            == 1
        )
        assert await session.scalar(text("select count(*) from project_guide_compilations")) == 1
        assert (
            await session.scalar(
                text("select count(*) from project_guide_component_projection_operations")
            )
            == 2
        )
        assert (
            await session.scalar(text("select count(*) from project_guide_setup_finalizations"))
            == 1
        )


@pytest.mark.parametrize("phase", ["delivery", "fence", "sufficiency", "policy", "finalization"])
async def test_each_phase_rechecks_service_authority_and_restoration_reuses_attempt(
    pending_source, scripted_model_profile, monkeypatch, phase
):
    from app.core.config import get_settings
    from app.modules.authorization.api import AuthorizationDenied
    from app.modules.projects.api import (
        ProjectGuideCompilationExecutionError,
        ProjectGuideSetupFinalizationError,
    )
    from app.modules.projects.api.guide_compilation_projections import ProjectGuideProjectionError

    monkeypatch.setenv("WORKSTREAM_CELERY_TASK_ALWAYS_EAGER", "true")
    get_settings.cache_clear()
    from app.workers import project_setup as worker

    factory, actor, setup_id, snapshot = pending_source
    await create_committed_document_fixture(snapshot["id"])
    await request_pending_source(factory, setup_id, scripted_model_profile)
    delivery = await _delivery(factory, setup_id)
    runtime = ScriptedGuideRuntime()
    monkeypatch.setattr(worker, "create_project_guide_runtime", lambda configuration: runtime)
    coordinator = await worker._coordinator(factory)

    async def revoke():
        async with factory() as session, session.begin():
            await session.execute(
                text(
                    "update actor_identity_links set status='revoked',revoked_at=now(),revoked_by='test',revoked_reason='phase revocation' where id=:id"
                ),
                {"id": str(actor.identity_link_id)},
            )

    owners = {
        "fence": (coordinator._execution._backend, "fence"),
        "sufficiency": (coordinator._projections, "project_guide_sufficiency"),
        "policy": (coordinator._projections, "project_submission_artifact_policy"),
        "finalization": (coordinator, "_finalize"),
    }
    if phase == "delivery":
        await revoke()
    else:
        owner, name = owners[phase]
        original = getattr(owner, name)

        async def revoked_call(*args, **kwargs):
            await revoke()
            return await original(*args, **kwargs)

        monkeypatch.setattr(owner, name, revoked_call)
    with pytest.raises(
        (
            AuthorizationDenied,
            ProjectGuideCompilationExecutionError,
            ProjectGuideProjectionError,
            ProjectGuideSetupFinalizationError,
        )
    ) as error:
        await coordinator.run(delivery)
    if phase != "delivery":
        assert error.value.code == "service_authority_denied"
    assert runtime.calls == (0 if phase in {"delivery", "fence"} else 1)
    async with factory() as session:
        assert (
            await session.scalar(text("select count(*) from project_guide_setup_finalizations"))
            == 0
        )
        assert (
            await session.scalar(
                text("select count(*) from project_guide_component_projection_operations")
            )
            == {"delivery": 0, "fence": 0, "sufficiency": 0, "policy": 1, "finalization": 2}[phase]
        )
    if phase != "delivery":
        monkeypatch.setattr(owner, name, original)
    async with factory() as session, session.begin():
        await session.execute(
            text(
                "update actor_identity_links set status='active',revoked_at=null,revoked_by=null,revoked_reason=null,reactivated_at=now(),reactivated_by='test',reactivation_reason='restore phase authority' where id=:id"
            ),
            {"id": str(actor.identity_link_id)},
        )
    receipt = await coordinator.run(delivery)
    assert receipt["status"] == "policy_draft_ready"
    assert runtime.calls == 1
    async with factory() as session:
        assert (
            await session.scalar(text("select count(*) from project_guide_compilation_attempts"))
            == 1
        )
        assert (
            await session.scalar(text("select count(*) from project_guide_setup_finalizations"))
            == 1
        )


@pytest.mark.parametrize("duplicate_observation", ["before_persist", "after_finalization"])
async def test_concurrent_live_deliveries_converge_on_one_finalization(
    pending_source, scripted_model_profile, monkeypatch, duplicate_observation
):
    """Both overlapping-delivery observations converge on one retained finalization."""
    import asyncio
    from app.core.config import get_settings

    monkeypatch.setenv("WORKSTREAM_CELERY_TASK_ALWAYS_EAGER", "true")
    get_settings.cache_clear()
    from app.workers import project_setup as worker

    factory, actor, setup_id, snapshot = pending_source
    await create_committed_document_fixture(snapshot["id"])
    await request_pending_source(factory, setup_id, scripted_model_profile)
    delivery = await _delivery(factory, setup_id)
    entered, both_entered = asyncio.Event(), asyncio.Event()
    first_provider_release, duplicate_provider_release = asyncio.Event(), asyncio.Event()
    persist_entered, persist_release = asyncio.Event(), asyncio.Event()
    active = 0
    runtime = ScriptedGuideRuntime()
    original = runtime.compile_project_guide

    async def blocked_provider(context, capabilities):
        nonlocal active
        active += 1
        release = first_provider_release if active == 1 else duplicate_provider_release
        entered.set()
        if active == 2:
            both_entered.set()
        await release.wait()
        return await original(context, capabilities)

    monkeypatch.setattr(runtime, "compile_project_guide", blocked_provider)
    monkeypatch.setattr(worker, "create_project_guide_runtime", lambda config: runtime)
    coordinator = await worker._coordinator(factory)
    persist = coordinator._execution._backend.persist

    async def blocked_persist(*args, **kwargs):
        persist_entered.set()
        await persist_release.wait()
        return await persist(*args, **kwargs)

    monkeypatch.setattr(coordinator._execution._backend, "persist", blocked_persist)
    first = asyncio.create_task(coordinator.run(delivery))
    duplicate = None
    try:
        await asyncio.wait_for(entered.wait(), timeout=20)
        duplicate = asyncio.create_task(
            (await worker._coordinator(factory)).run(delivery)
        )
        await asyncio.wait_for(both_entered.wait(), timeout=20)
        first_provider_release.set()
        await asyncio.wait_for(persist_entered.wait(), timeout=20)
        if duplicate_observation == "after_finalization":
            persist_release.set()
            receipt = await asyncio.wait_for(first, timeout=30)
        duplicate_provider_release.set()
        duplicate_receipt = await asyncio.wait_for(duplicate, timeout=30)
        if duplicate_observation == "before_persist":
            assert duplicate_receipt["status"] == "provider_result_accepted_not_persisted"
            persist_release.set()
            receipt = await asyncio.wait_for(first, timeout=30)
        else:
            assert duplicate_receipt == receipt
    finally:
        first_provider_release.set()
        duplicate_provider_release.set()
        persist_release.set()
        tasks = [task for task in (first, duplicate) if task is not None]
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
    assert receipt["status"] == "policy_draft_ready"
    assert runtime.calls == 2
    assert await (await worker._coordinator(factory)).run(delivery) == receipt
    assert runtime.calls == 2
    async with factory() as session:
        attempt_id = await session.scalar(text("select id from project_guide_compilation_attempts"))
        if duplicate_observation == "before_persist":
            assert duplicate_receipt["attempt_id"] == str(attempt_id)
        for table in [
            "project_guide_compilation_attempts",
            "project_guide_compilations",
            "project_guide_setup_finalizations",
        ]:
            assert await session.scalar(text("select count(*) from " + table)) == 1


@pytest.mark.parametrize(
    "field,value",
    [
        ("error_code", "stale"),
        ("error_summary", "stale"),
        ("started_at", "2026-01-01T00:00:00+00:00"),
        ("finished_at", "2026-01-01T00:00:00+00:00"),
        ("documents_ready_at", None),
        ("post_submit_derivation_summary", {"status": "stale"}),
    ],
)
async def test_dirty_delivery_rejects_before_provider_and_preserves_request(
    pending_source, monkeypatch, field, value
):
    from datetime import datetime
    from app.core.config import get_settings
    from app.modules.projects.models import ProjectSetupRun

    monkeypatch.setenv("WORKSTREAM_CELERY_TASK_ALWAYS_EAGER", "true")
    get_settings.cache_clear()
    from app.workers import project_setup as worker

    factory, actor, setup_id, snapshot = pending_source
    await create_committed_document_fixture(snapshot["id"])
    await request_pending_source(factory, setup_id, runtime_configuration())
    delivery = await _delivery(factory, setup_id)
    async with factory() as session, session.begin():
        setup = await session.get(ProjectSetupRun, str(setup_id))
        setattr(setup, field, datetime.fromisoformat(value) if field.endswith("_at") and value else value)

    def forbidden_runtime(_configuration):
        pytest.fail("dirty setup reached configuration or provider")

    monkeypatch.setattr(worker, "create_project_guide_runtime", forbidden_runtime)
    with pytest.raises(ProjectGuideCompilationDeliveryError):
        await (await worker._coordinator(factory)).run(delivery)
    async with factory() as session:
        for table in (
            "project_guide_compilation_request_operations",
            "project_guide_compilation_attempts",
            "project_guide_component_projection_operations",
            "project_guide_setup_finalizations",
        ):
            assert await session.scalar(text("select count(*) from " + table)) == (1 if table in {"project_guide_compilation_request_operations", "project_guide_compilation_attempts"} else 0)


async def test_stale_queued_delivery_uses_retained_configuration_after_settings_change(
    pending_source, scripted_model_profile, monkeypatch
):
    from app.core.config import get_settings
    from app.workers import project_setup as worker

    factory, _actor, setup_id, snapshot = pending_source
    await create_committed_document_fixture(snapshot["id"])
    configuration = scripted_model_profile
    await request_pending_source(factory, setup_id, configuration)
    delivery = await _delivery(factory, setup_id)
    await _reclaim_exact_delivery(factory, delivery, monkeypatch)
    # Admission has frozen the runtime. A later deployment setting cannot select
    # a new provider or make this retained delivery depend on fresh selection.
    monkeypatch.setenv("WORKSTREAM_PROJECT_AGENT_RUNTIME", "manager_authored")
    monkeypatch.setenv("WORKSTREAM_PROJECT_AGENT_MODEL", "changed-after-request")
    get_settings.cache_clear()
    runtime = ScriptedGuideRuntime(configuration)

    def retained_runtime(actual):
        assert actual == configuration
        return runtime

    monkeypatch.setattr(worker, "create_project_guide_runtime", retained_runtime)
    first = await (await worker._coordinator(factory)).run(delivery)
    assert first["status"] == "policy_draft_ready"
    assert await (await worker._coordinator(factory)).run(delivery) == first
    assert runtime.calls == 1
    assert delivery.source_snapshot_id not in await _published_continuation_snapshots(factory)


async def _remove_retained_runtime_configuration(factory):
    # Simulate the nullable additive-migration result using only this isolated
    # database. Production immutability is independently proved in SQL tests.
    async with factory() as session, session.begin():
        from scripts.run_isolated_tests import NAME_RE

        assert NAME_RE.fullmatch(await session.scalar(text("select current_database()")))
        await session.execute(
            text(
                "alter table project_guide_compilation_attempts disable trigger project_guide_runtime_configuration_guard"
            )
        )
        await session.execute(
            text(
                "alter table project_guide_compilation_attempts disable trigger trg_compilation_attempt_update"
            )
        )
        await session.execute(
            text(
                "update project_guide_compilation_attempts set runtime_configuration=null,runtime_configuration_hash=null"
            )
        )
        await session.execute(
            text(
                "alter table project_guide_compilation_attempts enable trigger project_guide_runtime_configuration_guard"
            )
        )
        await session.execute(
            text(
                "alter table project_guide_compilation_attempts enable trigger trg_compilation_attempt_update"
            )
        )


async def _reclaim_exact_delivery(factory, delivery, monkeypatch):
    """Prove Beat selection and queue publication preserve the owned delivery."""
    from app.modules.projects import setup_queue

    await _select_stale_delivery(factory, delivery)
    sent = []

    def enqueue(**kwargs):
        sent.append(kwargs)
        return kwargs["task_id"]

    monkeypatch.setattr(setup_queue, "enqueue_project_guide_compilation", enqueue)
    async with factory() as session:
        await setup_queue.dispatch_project_guide_compilation_after_commit(
            session,
            project_id=str(delivery.project_id),
            guide_id=str(delivery.guide_id),
            source_snapshot_id=str(delivery.source_snapshot_id),
            setup_run_id=str(delivery.setup_run_id),
            setup_generation=delivery.setup_generation,
        )
    assert sent == [
        {
            "project_id": str(delivery.project_id),
            "guide_id": str(delivery.guide_id),
            "source_snapshot_id": str(delivery.source_snapshot_id),
            "setup_run_id": str(delivery.setup_run_id),
            "setup_generation": delivery.setup_generation,
            "task_id": str(delivery.task_id),
        }
    ]


async def _select_stale_delivery(factory, delivery):

    async with factory() as session, session.begin():
        await session.execute(
            text(
                "update project_setup_runs set updated_at=now()-interval '2 minutes' where id=:id"
            ),
            {"id": str(delivery.setup_run_id)},
        )
    assert delivery.source_snapshot_id in await _published_continuation_snapshots(factory)


async def _published_continuation_snapshots(factory):
    """Exercise the current upload scanner and resolve its actual published puts."""
    from app.adapters.artifacts.internal_workers import scan_guide_setup_continuations

    published = []

    async def publish(put_id):
        published.append(str(put_id))

    count = await scan_guide_setup_continuations(publish)
    assert count == len(published)
    snapshots = set()
    async with factory() as session:
        for put_id in published:
            snapshot_id = await session.scalar(text(
                "select i.source_snapshot_id from artifact_put_attempts p "
                "join guide_source_snapshot_items i on i.id=p.guide_source_item_id "
                "where p.id=:id"
            ), {"id": put_id})
            assert snapshot_id is not None
            snapshots.add(UUID(str(snapshot_id)))
    return snapshots


_RULES_LABEL = "workstream-rules.json"


def _manager_rules(**overrides) -> bytes:
    """A manager-authored rules document citing the PDF original by SHA-256."""
    import json
    from .helpers import SOURCE_SHA256, valid_specification

    pre_specification = valid_specification().model_dump(mode="json")
    pre_specification["evaluation_method"] = "Inspect the candidate package manifest before submission."
    pre_specification["inputs"][0].update(
        input_id="candidate_package", purpose="Candidate package to inspect before submission."
    )
    pre_specification["check_steps"] = [
        "Inspect the candidate package manifest for the submission artifact."
    ]
    post_specification = valid_specification().model_dump(mode="json")
    post_specification["evaluation_method"] = (
        "Inspect the immutable submitted package manifest after submission."
    )
    post_specification["check_steps"] = [
        "Inspect the immutable package manifest for the submission artifact."
    ]

    return json.dumps({
        "format": "workstream.project_guide_rules.v1",
        "status": "draft_ready",
        "findings": [{"severity": "info", "code": "guide.ready", "message": "Guide is complete.",
                      "evidence_refs": [{"document": SOURCE_SHA256, "start_page": 1, "end_page": 1}]}],
        "submission_artifact_policy": {"maximum_file_size_bytes": 1000,
                                       "maximum_package_size_bytes": 10000,
                                       "required_artifacts": ["submission"]},
        "requirements": [
            {
                "suggestion_id": "submission_present_before_intake",
                "statement": "The package must include the submission artifact before intake.",
                "stage": "pre_submit",
                "classification_rationale": "The required artifact can be checked before Submission creation.",
                "check_specification": pre_specification,
                "evidence_refs": [],
            },
            {
                "suggestion_id": "submission_present_after_intake",
                "statement": "The submitted package must retain the submission artifact.",
                "stage": "post_submit",
                "classification_rationale": "The immutable submitted package can be evaluated after intake.",
                "check_specification": post_specification,
                "evidence_refs": [],
            },
        ],
        "setup_notes": [],
    } | overrides).encode()


@pytest.fixture
async def manager_authored_source(project_client, project_database_env, monkeypatch):  # noqa: F811
    """A guide with one PDF and one manager rules document, compiled with no provider."""
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from app.core.config import get_settings
    from app.modules.projects.models import ProjectSetupRun
    from tests.projects.guide_fixtures import create_guide, create_project, read_guide_source_snapshot

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("WORKSTREAM_CELERY_TASK_ALWAYS_EAGER", "true")
    get_settings.cache_clear()
    project = await create_project(project_client)
    guide = await create_guide(project_client, project["id"], {
        "version": "v1", "change_summary": "Manager-authored rules",
        "task_examples": [{"content": "Review a claim using the project guide."}],
        "documents": [{"label": "guide.pdf", "media_type": "application/pdf"},
                      {"label": _RULES_LABEL, "media_type": "text/markdown"}],
    })
    snapshot = await read_guide_source_snapshot(project["id"], guide["id"])
    engine = create_async_engine(project_database_env)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        setup = await session.scalar(
            select(ProjectSetupRun).where(ProjectSetupRun.source_snapshot_id == snapshot["id"]))
        setup_id = UUID(setup.id)
    try:
        yield factory, setup_id, snapshot
    finally:
        await engine.dispose()
        get_settings.cache_clear()


def _serve_documents(monkeypatch, worker, bodies):
    """Scripted ART grant serving each committed original's exact bytes."""
    from contextlib import asynccontextmanager
    from io import BytesIO
    from app.modules.projects.api.guide_documents import OpenGuideDocument

    @asynccontextmanager
    async def access(_sessions, _attempt_id, manifest, _configuration):
        class Documents:
            @asynccontextmanager
            async def open(self, handle):
                item = next(item for item in manifest.documents if manifest.handle_for(item) == handle)
                with BytesIO(bodies[item.sha256]) as stream:
                    yield OpenGuideDocument(item, stream)

            async def close(self):
                pass

        yield Documents()

    monkeypatch.setattr(worker, "guide_document_access_runtime", access)


@pytest.mark.parametrize("valid", [True, False], ids=["rules_ready", "rules_malformed"])
async def test_manager_authored_rules_compile_through_the_live_worker_without_inference(
    manager_authored_source, monkeypatch, valid
):
    import hashlib
    from app.workers import project_setup as worker
    from .helpers import SOURCE_BYTES, SOURCE_SHA256

    factory, setup_id, snapshot = manager_authored_source
    rules = _manager_rules() if valid else _manager_rules(status="draft_ready", findings="none")
    manifest = await create_committed_document_fixture(snapshot["id"], contents={_RULES_LABEL: rules})
    rules_sha256 = "sha256:" + hashlib.sha256(rules).hexdigest()
    assert {item.sha256 for item in manifest.documents} == {SOURCE_SHA256, rules_sha256}
    _serve_documents(monkeypatch, worker, {SOURCE_SHA256: SOURCE_BYTES, rules_sha256: rules})
    await request_pending_source(factory, setup_id, manager_runtime_configuration())
    delivery = await _delivery(factory, setup_id)

    outcome = await (await worker._coordinator(factory)).run(delivery)

    async with factory() as session:
        attempt = (await session.execute(text(
            "select id,status,failure_code,runtime_configuration::jsonb as configuration "
            "from project_guide_compilation_attempts where setup_run_id=:id"),
            {"id": str(setup_id)})).one()
        accesses = (await session.execute(text(
            "select source_item_id::text,attachment_allocation_id from project_guide_document_accesses "
            "where attempt_id=:id"), {"id": attempt.id})).all()
        allocations = await session.scalar(text(
            "select count(*) from project_guide_runtime_allocations where attempt_id=:id"),
            {"id": attempt.id})
        compilation = await session.scalar(text(
            "select canonical_result::jsonb from project_guide_compilations where attempt_id=:id"),
            {"id": attempt.id})
    # Provenance: the stored snapshot states that no provider or model ran.
    assert {key: attempt.configuration[key] for key in
            ("runtime_key", "model_provider", "model_api", "model")} == {
        "runtime_key": "manager_authored", "model_provider": "none",
        "model_api": "none", "model": "none"}
    assert allocations == 0
    assert sorted(row[0] for row in accesses) == sorted(
        str(item.source_item_id) for item in manifest.documents)
    assert {row[1] for row in accesses} == {None}
    if not valid:
        assert (attempt.status, attempt.failure_code) == ("compilation_invalid_terminal", "schema_invalid")
        assert outcome["attempt_id"] == str(attempt.id)
        assert compilation is None
        return
    assert outcome["status"] == "policy_draft_ready"
    assert attempt.status == "compilation_persisted"
    rules_item = next(item for item in manifest.documents if item.sha256 == rules_sha256)
    [finding] = compilation["findings"]
    assert [ref["sha256"] for ref in finding["evidence_refs"]] == [SOURCE_SHA256, rules_sha256]
    assert finding["evidence_refs"][1]["source_item_id"] == str(rules_item.source_item_id)
    assert [(item["suggestion_id"], item["stage"]) for item in compilation["requirements"]] == [
        ("submission_present_before_intake", "pre_submit"),
        ("submission_present_after_intake", "post_submit"),
    ]
    for suggestion in compilation["requirements"]:
        [evidence] = suggestion["evidence_refs"]
        assert evidence["sha256"] == rules_sha256
        assert evidence["source_item_id"] == str(rules_item.source_item_id)
        assert suggestion["check_specification"]["check_steps"]
