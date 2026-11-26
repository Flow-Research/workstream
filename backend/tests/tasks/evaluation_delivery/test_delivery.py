"""Actual request delivery, exact terminal replay, and hidden production scope."""

import pytest
from sqlalchemy import select, func

from app.adapters.outbox import production_outbox_delivery
from app.modules.actors.api import ServiceIdentity
from app.modules.checkers.api.execution import CheckerExecutionUnavailable, REQUEST_EVENT
from app.modules.outbox.api import FinalizationCause, HandlerOutcome
from app.modules.tasks.models import WorkstreamTask
from app.modules.tasks.post_submit_routing.models import TaskRoutingRequest, TaskPostSubmitRoutingManifest
from app.modules.reviews.decision.models import Review
from app.modules.reviews.acceptance.models import FinalAcceptance
from app.modules.contributions.records.models import ContributionRecord
from app.modules.compensation.awards.models import CompensationAward
from tests.checkers.execution.support import service_link_state
from tests.post_submit_materialization_helpers import material_fixture
from .support import delivery_fixture, invoked, state, outcome


@pytest.mark.parametrize("provider", ["local", "minio"])
async def test_shared_delivery_runs_exact_request_once(tmp_path, isolated_database_env, provider):
    if provider == "minio":
        from tests.test_s3_artifact_store import provision_minio_bucket
        await provision_minio_bucket.__wrapped__()
    async with material_fixture(tmp_path, isolated_database_env, provider=provider) as h:
        d = await delivery_fixture(h)
        assert (REQUEST_EVENT, 1) in production_outbox_delivery(h.factory)._registry.keys
        receipt = await d.delivery.deliver(h.created.evaluation_event_id, h.request.project_id, "worker")
        assert outcome(receipt)["delivery_state"] == "acknowledged"
        saved = await state(h)
        assert saved["run"]["status"] == "completed"
        assert saved["run"]["worker_lease_generation"] == 1
        assert set(saved["allows"]) == {saved["run"]["execute_evidence_id"], saved["run"]["finalize_evidence_id"]}
        assert len(saved["allows"]) == 2 and saved["events"] == 1
        assert saved["members"] == 1
        assert len(d.selected.requests) == 1
        assert d.selected.requests[0].identity.phase == "post_submit"
        assert saved["run"]["material_custody"] == {
            "submission_id": str(h.created.submission_id), "submission_version": h.created.submission_version,
            "admission_id": str(h.created.admission_id), "binding_id": str(h.created.artifact_binding_id),
            "content_id": str(h.created.artifact_content_id), "replica_id": str(h.replica_id),
            "content_sha256": h.request.content_sha256, "byte_count": len(h.data),
            "semantic_manifest_sha256": h.manifest.sha256,
        }
        assert await d.delivery.deliver(h.created.evaluation_event_id, h.request.project_id, "duplicate") is None
        assert await state(h) == saved
        assert len(h.store.opens) == 1 and not h.preparation._active
        async with h.factory() as session:
            for model in (TaskRoutingRequest, TaskPostSubmitRoutingManifest, Review,
                          FinalAcceptance, ContributionRecord, CompensationAward):
                assert await session.scalar(select(func.count()).select_from(model)) == 0
            assert await session.scalar(select(WorkstreamTask.status).where(
                WorkstreamTask.id == str(h.request.task_id),
            )) == "evaluation_pending"


async def test_lost_ack_terminal_replay_rechecks_authority_without_material(tmp_path, isolated_database_env):
    async with material_fixture(tmp_path, isolated_database_env) as h:
        d = await delivery_fixture(h)
        envelope = await invoked(h, d)
        assert await d.handler(envelope) is HandlerOutcome.ACKNOWLEDGE
        saved = await state(h)
        assert await d.handler(envelope) is HandlerOutcome.ACKNOWLEDGE
        assert await state(h) == saved and len(h.store.opens) == 1
        await service_link_state(h.factory, ServiceIdentity.CHECKER_POST_SUBMIT, active=False)
        with pytest.raises(CheckerExecutionUnavailable):
            await d.handler(envelope)
        assert await state(h) == saved and len(h.store.opens) == 1
        await service_link_state(h.factory, ServiceIdentity.CHECKER_POST_SUBMIT, active=True)
        assert await d.handler(envelope) is HandlerOutcome.ACKNOWLEDGE
        await d.delivery.finalize(envelope.claim, FinalizationCause.ACKNOWLEDGE)
        assert await d.handler(envelope) is HandlerOutcome.REJECT
        assert await state(h) == saved


async def test_missing_checker_authority_is_unknown_not_retry(tmp_path, isolated_database_env):
    async with material_fixture(tmp_path, isolated_database_env, provision_checker=False) as h:
        d = await delivery_fixture(h)
        before = await state(h)
        receipt = await d.delivery.deliver(h.created.evaluation_event_id, h.request.project_id, "worker")
        assert outcome(receipt)["invocation_unknown"] is True
        assert outcome(receipt)["next_attempt_at"] is None
        assert await state(h) == before and not h.store.opens and not h.preparation._active
        assert await d.delivery.deliver(h.created.evaluation_event_id, h.request.project_id, "again") is None


async def test_task_eligibility_blocks_new_effect_but_not_exact_terminal_replay(
    tmp_path, isolated_database_env, monkeypatch,
):
    from app.modules.tasks.post_submit_routing.evaluation_guard import TaskEvaluationGuard

    async with material_fixture(tmp_path, isolated_database_env) as h:
        d = await delivery_fixture(h)
        envelope = await invoked(h, d)
        original = TaskEvaluationGuard.lock_evaluation_scope
        eligible = False

        async def controlled(guard, request):
            # Keep all real ownership checks and TASK locks, vary only eligibility.
            assert await original(guard, request) is True
            return eligible

        monkeypatch.setattr(TaskEvaluationGuard, "lock_evaluation_scope", controlled)
        before = await state(h)
        with pytest.raises(CheckerExecutionUnavailable, match="checker_delivery_execution_unavailable"):
            await d.handler(envelope)
        assert await state(h) == before and not h.store.opens
        eligible = True
        assert await d.handler(envelope) is HandlerOutcome.ACKNOWLEDGE
        terminal = await state(h)
        eligible = False
        assert await d.handler(envelope) is HandlerOutcome.ACKNOWLEDGE
        assert await state(h) == terminal and len(h.store.opens) == 1


@pytest.mark.parametrize("rollback", [False, True])
async def test_known_post_failure_schedules_one_delayed_service_retry(
    tmp_path, isolated_database_env, monkeypatch, rollback,
):
    """Retain one exact successor for known failure, or roll it all back."""
    from datetime import timedelta

    from app.adapters.checkers import evaluation_coordinator
    from app.modules.checkers.api.materialization import PostSubmissionMaterializationFailure
    from app.modules.checkers.models import CheckerRetryReceipt, CheckerRun, CheckerSubmissionFence
    from app.modules.outbox.api import OutboxPersistenceError
    from app.modules.outbox.models import OutboxEvent
    from app.modules.outbox.service import OutboxService

    class MissingMaterial:
        async def materialize(self, _facts, _consumer):
            raise PostSubmissionMaterializationFailure("controlled missing material")

    async with material_fixture(tmp_path, isolated_database_env) as h:
        d = await delivery_fixture(h, materialization=MissingMaterial())
        original_append = OutboxService.append

        async def guarded_append(outbox, event):
            if event.idempotency_key.startswith("checker-auto-retry:"):
                raise OutboxPersistenceError("controlled retry persistence failure")
            return await original_append(outbox, event)

        if rollback:
            monkeypatch.setattr(OutboxService, "append", guarded_append)
        receipt = outcome(await d.delivery.deliver(h.created.evaluation_event_id, h.request.project_id, "worker"))
        assert receipt["delivery_state"] == ("dead_letter" if rollback else "acknowledged")
        assert receipt["invocation_unknown"] is rollback
        async with h.factory.begin() as session:
            runs = list(await session.scalars(select(CheckerRun).where(
                CheckerRun.submission_id == str(h.request.submission_id),
            ).order_by(CheckerRun.evaluation_generation)))
            original = runs[0]
            fence = await session.get(CheckerSubmissionFence, original.submission_id)
            assert await session.scalar(select(func.count()).select_from(CheckerRetryReceipt)) == 0
            assert not d.selected.requests
            if rollback:
                assert len(runs) == 1 and fence.current_run_id == original.id
                assert original.status == "running" and original.result_json is None
                return
            assert len(runs) == 2
            successor = runs[1]
            assert fence.current_run_id == successor.id
            assert original.status == "infrastructure_failed" and original.failure_code == "material_unavailable"
            assert successor.status == "queued" and successor.supersedes_checker_run_id == original.id
            new_event = await session.get(OutboxEvent, successor.retry_delivery_event_id)
            assert new_event.not_before_at == original.completed_at + timedelta(seconds=5)
            event_id, due = new_event.event_id, new_event.not_before_at
            assert (await evaluation_coordinator(session).classify_uncertain_delivery(h.request)).classification == "committed"
            read = await evaluation_coordinator(session).read_current_progress(
                project_id=h.request.project_id, task_id=h.request.task_id,
                submission_id=h.request.submission_id, original_request_id=h.request.evaluation_request_id,
            )
            assert read.current.reservation.evaluation_generation == 2
            assert read.previous_failure_code == "material_unavailable"
            assert read.retry_event_id == event_id
            assert new_event.payload["source_finalize_evidence_id"] == original.finalize_evidence_id
        async with h.factory() as session:
            now = await session.scalar(select(func.clock_timestamp()))
            if now < due:
                assert await d.delivery.claim(event_id, h.request.project_id, "worker") is None
        assert await d.delivery.deliver(h.created.evaluation_event_id, h.request.project_id, "duplicate") is None
