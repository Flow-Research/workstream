"""Real coordinator/custody with scripted document and model-provider ports."""

from uuid import UUID, uuid4

import pytest
from sqlalchemy import text

from app.modules.projects.api.guide_compilation import ProjectGuideCompilationDelivery
from app.modules.projects.api.setup_identity import project_guide_compilation_task_id
from app.modules.projects.api.guide_compilation import ProjectGuideCompilationDeliveryError
from tests.committed_guide_fixtures import create_committed_document_fixture
from tests.projects.client_fixtures import (
    project_client as project_client,
    project_database_env as project_database_env,
)
from .test_automatic_request import automatic_source as automatic_source
from .helpers import runtime_configuration, result
from .runtime_fixtures import document_access, record_scripted_document_access
from app.interfaces.project_agents import GuideEvidenceRef


@pytest.fixture(autouse=True)
def scripted_document_port(monkeypatch):
    monkeypatch.setenv("WORKSTREAM_CELERY_BROKER_URL", "memory://")
    monkeypatch.setenv("WORKSTREAM_CELERY_RESULT_BACKEND", "cache+memory://")
    from app.core.config import get_settings
    get_settings.cache_clear()
    from app.workers import project_setup as worker
    monkeypatch.setattr(worker, "guide_document_access_runtime",
                        lambda sessions, *args: document_access(*args))


async def _delivery(factory, setup_id):
    async with factory() as session, session.begin():
        row = (
            await session.execute(
                text(
                    "select project_id,guide_id,source_snapshot_id,setup_generation from project_setup_runs where id=:id"
                ),
                {"id": str(setup_id)},
            )
        ).one()
        task_id = project_guide_compilation_task_id(str(setup_id), row.setup_generation)
        await session.execute(
            text(
                "update project_setup_runs set status='dispatch_pending',current_step='dispatch',celery_task_id=:task where id=:id"
            ),
            {"id": str(setup_id), "task": task_id},
        )
    return ProjectGuideCompilationDelivery(
        project_id=row.project_id,
        guide_id=row.guide_id,
        source_snapshot_id=row.source_snapshot_id,
        setup_run_id=setup_id,
        setup_generation=row.setup_generation,
        task_id=task_id,
    )


class Runtime:
    outcome = result()
    identity = runtime_configuration().adapter_identity
    calls = 0

    def admit_execution(self):
        pass

    async def aclose(self):
        pass

    async def compile_project_guide(self, context, capabilities):
        self.calls += 1
        await record_scripted_document_access(context, capabilities)
        if isinstance(self.outcome, Exception):
            raise self.outcome
        refs = tuple(GuideEvidenceRef(source_item_id=item.source_item_id,
                     document_version_id=item.ingest_id, sha256=item.sha256)
                     for item in context.material.documents)
        return self.outcome.model_copy(update={
            field: tuple(item.model_copy(update={"evidence_refs": refs})
                         for item in getattr(self.outcome, field))
            for field in ("findings", "requirements", "capability_suggestions")
        })


@pytest.mark.parametrize("status", ["draft_ready", "draft_ready_with_warnings", "guide_blocked"])
async def test_pending_exact_delivery_compiles_once_and_replays_finalization(
    automatic_source, monkeypatch, status, project_client
):  # noqa: F811
    monkeypatch.setenv("WORKSTREAM_CELERY_TASK_ALWAYS_EAGER", "true")
    from app.core.config import get_settings

    get_settings.cache_clear()
    from app.workers import project_setup as worker

    factory, actor, setup_id, snapshot = automatic_source
    await create_committed_document_fixture(snapshot["id"])
    delivery = await _delivery(factory, setup_id)
    runtime = Runtime()
    if status != "draft_ready":
        from app.interfaces.project_agents import CompilationFinding

        runtime.outcome = result().model_copy(
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
                else result().submission_artifact_policy,
            }
        )
    monkeypatch.setattr(worker, "create_project_guide_runtime", lambda configuration: runtime)
    monkeypatch.setattr(
        worker, "project_guide_runtime_configuration", lambda settings: runtime_configuration()
    )
    coordinator = worker._coordinator(factory)
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

    def forbidden(*args):
        pytest.fail("finalized replay reached request configuration or runtime construction")

    monkeypatch.setattr(worker, "create_project_guide_runtime", forbidden)
    monkeypatch.setattr(worker, "project_guide_runtime_configuration", forbidden)
    replay = await worker._coordinator(factory).run(delivery)
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
        await worker._coordinator(factory).run(delivery)
    assert denied.value.code == "service_authority_denied"
    assert runtime.calls == 1


@pytest.mark.parametrize(
    "field",
    ["project_id", "guide_id", "source_snapshot_id", "setup_run_id", "setup_generation", "task_id"],
)
async def test_stale_delivery_rejects_before_any_compilation_effect(
    automatic_source, monkeypatch, field
):
    monkeypatch.setenv("WORKSTREAM_CELERY_TASK_ALWAYS_EAGER", "true")
    from app.core.config import get_settings

    get_settings.cache_clear()
    from app.workers import project_setup as worker

    factory, actor, setup_id, snapshot = automatic_source
    await create_committed_document_fixture(snapshot["id"])
    delivery = await _delivery(factory, setup_id)

    def forbidden(*args):
        pytest.fail("stale delivery reached configuration or runtime")

    monkeypatch.setattr(worker, "create_project_guide_runtime", forbidden)
    monkeypatch.setattr(worker, "project_guide_runtime_configuration", forbidden)
    changed = delivery.model_copy(update={field: 2 if field == "setup_generation" else uuid4()})
    async with factory() as session:
        before = await session.scalar(text("select count(*) from audit_events"))
    with pytest.raises(ProjectGuideCompilationDeliveryError, match="^stale compilation delivery$"):
        await worker._coordinator(factory).run(changed)
    async with factory() as session:
        assert await session.scalar(text("select count(*) from audit_events")) == before
        for table in [
            "project_guide_compilation_request_operations",
            "project_guide_compilation_attempts",
            "project_guide_component_projection_operations",
            "project_guide_setup_finalizations",
        ]:
            assert await session.scalar(text("select count(*) from " + table)) == 0


@pytest.mark.parametrize("outcome", ["invalid", "uncertain"])
async def test_invalid_or_uncertain_attempt_reports_durable_diagnostics_without_projection(
    automatic_source, monkeypatch, outcome, project_client
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

    factory, actor, setup_id, snapshot = automatic_source
    await create_committed_document_fixture(snapshot["id"])
    delivery = await _delivery(factory, setup_id)
    runtime = Runtime()
    runtime.outcome = (
        ProjectGuideCompilationInvalidOutputError("schema_invalid")
        if outcome == "invalid"
        else ProjectAgentRuntimeError("private-provider-detail")
    )
    monkeypatch.setattr(worker, "create_project_guide_runtime", lambda configuration: runtime)
    monkeypatch.setattr(
        worker, "project_guide_runtime_configuration", lambda settings: runtime_configuration()
    )
    coordinator = worker._coordinator(factory)
    # Beat selects the exact delivery before terminal provider custody exists.
    await _select_stale_delivery(factory, delivery)
    first = await coordinator.run(delivery)
    replay = await coordinator.run(delivery)
    assert first == replay
    assert runtime.calls == 1
    assert first["status"] == (
        "compilation_invalid_terminal" if outcome == "invalid" else "provider_outcome_unresolved"
    )
    assert first["error_code"] == (
        "schema_invalid" if outcome == "invalid" else "provider_outcome_unresolved"
    )
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


async def test_finalized_receipt_excludes_every_recovery_shape(automatic_source, monkeypatch):
    from app.workers import project_setup as worker

    factory, _actor, setup_id, snapshot = automatic_source
    await create_committed_document_fixture(snapshot["id"])
    delivery = await _delivery(factory, setup_id)
    runtime = Runtime()
    monkeypatch.setattr(worker, "create_project_guide_runtime", lambda configuration: runtime)
    monkeypatch.setattr(
        worker, "project_guide_runtime_configuration", lambda settings: runtime_configuration()
    )
    await _select_stale_delivery(factory, delivery)
    receipt = await worker._coordinator(factory).run(delivery)
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
    automatic_source, monkeypatch
):
    import asyncio
    import threading
    from app.core.config import get_settings
    from app.modules.projects import setup_queue

    monkeypatch.setenv("WORKSTREAM_CELERY_TASK_ALWAYS_EAGER", "true")
    get_settings.cache_clear()
    from app.workers import project_setup as worker

    factory, actor, setup_id, snapshot = automatic_source
    await create_committed_document_fixture(snapshot["id"])
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
    runtime = Runtime()
    monkeypatch.setattr(worker, "create_project_guide_runtime", lambda configuration: runtime)
    monkeypatch.setattr(
        worker, "project_guide_runtime_configuration", lambda settings: runtime_configuration()
    )

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
        receipt = await worker._coordinator(factory).run(delivery)
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
    automatic_source, monkeypatch, boundary
):
    from app.core.config import get_settings

    monkeypatch.setenv("WORKSTREAM_CELERY_TASK_ALWAYS_EAGER", "true")
    get_settings.cache_clear()
    from app.workers import project_setup as worker

    factory, actor, setup_id, snapshot = automatic_source
    await create_committed_document_fixture(snapshot["id"])
    delivery = await _delivery(factory, setup_id)
    runtime = Runtime()
    monkeypatch.setattr(worker, "create_project_guide_runtime", lambda configuration: runtime)
    monkeypatch.setattr(
        worker, "project_guide_runtime_configuration", lambda settings: runtime_configuration()
    )
    coordinator = worker._coordinator(factory)
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


@pytest.mark.parametrize("phase", ["request", "fence", "sufficiency", "policy", "finalization"])
async def test_each_phase_rechecks_service_authority_and_restoration_reuses_attempt(
    automatic_source, monkeypatch, phase
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

    factory, actor, setup_id, snapshot = automatic_source
    await create_committed_document_fixture(snapshot["id"])
    delivery = await _delivery(factory, setup_id)
    runtime = Runtime()
    monkeypatch.setattr(worker, "create_project_guide_runtime", lambda configuration: runtime)
    monkeypatch.setattr(
        worker, "project_guide_runtime_configuration", lambda settings: runtime_configuration()
    )
    coordinator = worker._coordinator(factory)

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
    if phase == "request":
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
    if phase != "request":
        assert error.value.code == "service_authority_denied"
    assert runtime.calls == (0 if phase in {"request", "fence"} else 1)
    async with factory() as session:
        assert (
            await session.scalar(text("select count(*) from project_guide_setup_finalizations"))
            == 0
        )
        assert (
            await session.scalar(
                text("select count(*) from project_guide_component_projection_operations")
            )
            == {"request": 0, "fence": 0, "sufficiency": 0, "policy": 1, "finalization": 2}[phase]
        )
    if phase != "request":
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


async def test_concurrent_live_deliveries_share_one_provider_and_finalization(
    automatic_source, monkeypatch
):
    import asyncio
    from app.core.config import get_settings

    monkeypatch.setenv("WORKSTREAM_CELERY_TASK_ALWAYS_EAGER", "true")
    get_settings.cache_clear()
    from app.workers import project_setup as worker

    factory, actor, setup_id, snapshot = automatic_source
    await create_committed_document_fixture(snapshot["id"])
    delivery = await _delivery(factory, setup_id)
    entered, release = asyncio.Event(), asyncio.Event()
    runtime = Runtime()
    original = runtime.compile_project_guide

    async def blocked_provider(context, capabilities):
        entered.set()
        await release.wait()
        return await original(context, capabilities)

    monkeypatch.setattr(runtime, "compile_project_guide", blocked_provider)
    monkeypatch.setattr(worker, "create_project_guide_runtime", lambda config: runtime)
    monkeypatch.setattr(
        worker, "project_guide_runtime_configuration", lambda settings: runtime_configuration()
    )
    first = asyncio.create_task(worker._coordinator(factory).run(delivery))
    try:
        await asyncio.wait_for(entered.wait(), timeout=20)
        duplicate = await asyncio.wait_for(worker._coordinator(factory).run(delivery), timeout=20)
        assert duplicate["error_code"] == "provider_outcome_unresolved"
    finally:
        release.set()
    receipt = await asyncio.wait_for(first, timeout=30)
    assert receipt["status"] == "policy_draft_ready"
    assert runtime.calls == 1
    assert await worker._coordinator(factory).run(delivery) == receipt
    async with factory() as session:
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
async def test_dirty_setup_rejects_before_request_or_provider(
    automatic_source, monkeypatch, field, value
):
    from datetime import datetime
    from app.core.config import get_settings
    from app.modules.projects.models import ProjectSetupRun

    monkeypatch.setenv("WORKSTREAM_CELERY_TASK_ALWAYS_EAGER", "true")
    get_settings.cache_clear()
    from app.workers import project_setup as worker

    factory, actor, setup_id, snapshot = automatic_source
    delivery = await _delivery(factory, setup_id)
    async with factory() as session, session.begin():
        setup = await session.get(ProjectSetupRun, str(setup_id))
        setattr(setup, field, datetime.fromisoformat(value) if field.endswith("_at") and value else value)

    def forbidden(*args):
        pytest.fail("dirty setup reached configuration or provider")

    monkeypatch.setattr(worker, "create_project_guide_runtime", forbidden)
    monkeypatch.setattr(worker, "project_guide_runtime_configuration", forbidden)
    with pytest.raises(ProjectGuideCompilationDeliveryError):
        await worker._coordinator(factory).run(delivery)
    async with factory() as session:
        for table in (
            "project_guide_compilation_request_operations",
            "project_guide_compilation_attempts",
            "project_guide_component_projection_operations",
            "project_guide_setup_finalizations",
        ):
            assert await session.scalar(text("select count(*) from " + table)) == 0


async def test_stale_queued_configuration_failure_is_reclaimed_and_finishes_same_delivery(
    automatic_source, monkeypatch
):
    from app.core.config import get_settings

    monkeypatch.setenv("WORKSTREAM_CELERY_TASK_ALWAYS_EAGER", "true")
    get_settings.cache_clear()
    from app.workers import project_setup as worker

    factory, actor, setup_id, snapshot = automatic_source
    await create_committed_document_fixture(snapshot["id"])
    delivery = await _delivery(factory, setup_id)

    def unavailable(settings):
        raise ValueError("missing runtime configuration")

    monkeypatch.setattr(worker, "project_guide_runtime_configuration", unavailable)
    for _ in range(4):
        with pytest.raises(ValueError, match="missing runtime configuration"):
            await worker._coordinator(factory).run(delivery)
    async with factory() as session:
        assert (
            await session.scalar(text("select count(*) from project_guide_compilation_attempts"))
            == 0
        )
    await _reclaim_exact_delivery(factory, delivery, monkeypatch)
    runtime = Runtime()
    monkeypatch.setattr(
        worker, "project_guide_runtime_configuration", lambda settings: runtime_configuration()
    )
    monkeypatch.setattr(worker, "create_project_guide_runtime", lambda configuration: runtime)
    first = await worker._coordinator(factory).run(delivery)
    assert first["status"] == "policy_draft_ready"
    assert await worker._coordinator(factory).run(delivery) == first
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

    from unittest.mock import patch

    with patch("app.adapters.artifacts.internal_workers.get_session_factory", return_value=factory):
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
            snapshots.add(UUID(snapshot_id))
    return snapshots
