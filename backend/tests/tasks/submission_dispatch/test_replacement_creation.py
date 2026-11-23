"""Real checker-remediation creation races, replay, and rollback."""

import asyncio

import pytest
from sqlalchemy import func, select, text

from app.adapters.checkers import evaluation_coordinator
from app.core.identifiers import new_record_id
from app.modules.artifacts.models import SubmissionBundleAdmission
from app.modules.outbox.api import OutboxPersistenceError
from app.modules.outbox.models import OutboxEvent
from app.modules.tasks.api import (
    TaskSubmissionContextUnavailable,
)
from app.modules.tasks.models import Submission, SubmissionDispatch
from app.modules.tasks.repository import TaskRepository
from tests.checkers.post_submit.support import change_request
from tests.tasks.post_submit_routing.remediation_support import remediation_source
from tests.tasks.post_submit_routing.support import revision_archive
from tests.test_submission_predecessor_custody import (
    _fixture_revision_context,
)


def _revision_command(h, root, data):
    """Build current foreground owners with exact routed revision acknowledgement."""
    from uuid import UUID
    from app.modules.artifacts.api.submission_intake import SubmissionIntakeMetadata
    from tests.artifacts.test_submission_pre_source import _source_runtime
    from tests.retained_material_fixtures import _foreground
    root.mkdir()
    runtime, errors = _source_runtime(data, root, "completed")
    command = _foreground(h.factory, h.actor_context, h.namespace, h.store.wrapped, runtime)
    metadata = SubmissionIntakeMetadata(
        task_id=h.request.task_id, assignment_id=h.request.assignment_id,
        predecessor_submission_id=h.created.submission_id,
        revision_preparation_id=UUID(str(h.revision_preparation_id)),
        revision_preparation_sha256=h.revision_preparation_sha256,
        summary=h.creation_request.summary,
        contributor_attestation=h.creation_request.contributor_attestation,
    )
    return command, metadata, errors


async def _creation_snapshot(h):
    """Capture every mutable owner participating in canonical creation."""
    async with h.factory() as session:
        row = (
            await session.execute(
                text(
                    """
                    SELECT
                      (SELECT jsonb_agg(to_jsonb(s)-ARRAY['attempt_status','status_reason',
                                'decided_at','updated_at'] ORDER BY s.id)
                         FROM public.submissions s),
                      (SELECT jsonb_agg(to_jsonb(d) ORDER BY d.submission_id)
                         FROM public.submission_dispatches d),
                      (SELECT jsonb_agg(to_jsonb(b) ORDER BY b.id)
                         FROM public.artifact_bindings b),
                      (SELECT jsonb_agg(to_jsonb(r) ORDER BY r.admission_id)
                         FROM public.submission_binding_receipts r),
                      (SELECT jsonb_agg(to_jsonb(a) ORDER BY a.id)
                         FROM public.submission_bundle_admissions a),
                      (SELECT jsonb_agg(to_jsonb(e) ORDER BY e.id)
                         FROM public.audit_events e
                        WHERE e.action_id IN (
                          'submission.create',
                          'artifact.submission.binding.create'
                        )),
                      (SELECT jsonb_agg(to_jsonb(r) ORDER BY r.id)
                         FROM public.checker_runs r),
                      (SELECT jsonb_agg(to_jsonb(f) ORDER BY f.submission_id)
                         FROM public.checker_submission_fences f),
                      (SELECT jsonb_agg(to_jsonb(e) ORDER BY e.event_id)
                         FROM public.outbox_events e),
                      (SELECT jsonb_agg(to_jsonb(t) ORDER BY t.id)
                         FROM public.workstream_tasks t)
                    """
                )
            )
        ).one()
    return tuple(row)


async def _admission_status(h, admission_id):
    async with h.factory() as session:
        admission = await session.get(SubmissionBundleAdmission, str(admission_id))
        assert admission is not None
        return admission.status


async def test_stale_routed_cause_denies_acceptance_after_successful_pre(
    tmp_path, isolated_database_env, monkeypatch,
):
    """A newer predecessor evaluation between PRE and T4 prevents acceptance."""
    from app.modules.artifacts.intake.models import SubmissionIntakeOperation, SubmissionSourceCharge
    from app.modules.tasks.models import WorkstreamTask
    from app.modules.checkers.api.execution import CheckerExecutionUnavailable
    from tests.post_submit_materialization_helpers import _submit_current_source

    async with remediation_source(tmp_path, isolated_database_env) as h:
        await _fixture_revision_context(h)
        data = revision_archive(h.data)
        command, metadata, errors = _revision_command(h, tmp_path / "stale-runtime", data)
        execute = command._execute
        observed = []
        async def supersede_after_pre(reservation):
            completion = await execute(reservation)
            assert completion.terminal.execution.eligible is True
            successor = change_request(h.request, evaluation_request_id=new_record_id(),
                                       evaluation_generation=h.request.evaluation_generation + 1)
            async with h.factory.begin() as session:
                reserved = await evaluation_coordinator(session).reserve_current_evaluation(successor)
            assert reserved.request_id == successor.evaluation_request_id
            observed.append((reservation, await _creation_snapshot(h)))
            return completion
        monkeypatch.setattr(command, "_execute", supersede_after_pre)
        with pytest.raises(TaskSubmissionContextUnavailable, match="^task_submission_context_invalid$") as denied:
            await _submit_current_source(h.factory, h.actor_context, command, metadata, data)
        assert isinstance(denied.value.__cause__, CheckerExecutionUnavailable)
        assert len(observed) == 1 and not errors, errors
        assert (await _creation_snapshot(h))[:9] == observed[0][1][:9]
        async with h.factory() as session:
            operation = await session.get(SubmissionIntakeOperation,
                                          str(observed[0][0].source.location.operation_id))
            assert operation is not None and operation.state == "failed"
            assert operation.acceptance_receipt is None and operation.finalization_event_id is None
            charge = await session.get(SubmissionSourceCharge, operation.id)
            assert charge.state == "sealed" and charge.accounted_bytes > 0
            task = await session.get(WorkstreamTask, str(h.request.task_id))
            assert task.status == "needs_revision" and task.active_submission_operation_id is None
            assert await session.scalar(select(func.count()).select_from(Submission).where(
                Submission.task_id == str(h.request.task_id), Submission.version == 2)) == 0


async def test_competing_revision_intakes_commit_one_and_winner_replays_exactly(
    tmp_path, isolated_database_env, monkeypatch,
):
    """Real T1 row-lock contention denies the loser before bytes; one winner reaches T5."""
    from contextvars import ContextVar
    from types import SimpleNamespace
    from uuid import UUID
    from app.modules.artifacts.intake.models import SubmissionIntakeOperation, SubmissionSourceCharge
    from tests.retained_material_fixtures import finalize_retained_intake

    async with remediation_source(tmp_path, isolated_database_env) as h:
        source_id = await _fixture_revision_context(h)
        first_data = revision_archive(h.data)
        second_data = revision_archive(first_data)
        commands = [_revision_command(h, tmp_path / name, data) for name, data in (
            ("first-runtime", first_data), ("second-runtime", second_data))]
        keys = [new_record_id(), new_record_id()]
        label = ContextVar("revision_intake_contender", default=None)
        held, release, entered, loser_done = (asyncio.Event() for _ in range(4))
        contender_pid, body_reads = [], []
        original_get_task = TaskRepository.get_task
        async def pause_with_task_lock(repository, *args, **kwargs):
            selected = label.get()
            if selected is not None:
                label.set(None)
            if selected == 1:
                contender_pid.append(await repository._session.scalar(text("SELECT pg_catalog.pg_backend_pid()")))
                entered.set()
            task = await original_get_task(repository, *args, **kwargs)
            if selected == 0:
                held.set()
                await asyncio.wait_for(release.wait(), 30)
            return task
        async def body(index):
            if index == 0:
                await asyncio.wait_for(loser_done.wait(), 30)
            body_reads.append(index)
            yield first_data if index == 0 else second_data
        async def submit(index):
            label.set(index)
            command, metadata, _ = commands[index]
            try:
                return await command.submit(metadata, body(index),
                    actor_id=h.actor_context.actor_profile_id, identity_link_id=h.actor_context.identity_link_id,
                    idempotency_key=keys[index], declared_raw_bytes=len(first_data if index == 0 else second_data))
            finally:
                if index == 1:
                    loser_done.set()
        first = second = None
        with monkeypatch.context() as patch:
            patch.setattr(TaskRepository, "get_task", pause_with_task_lock)
            try:
                first = asyncio.create_task(submit(0))
                await asyncio.wait_for(held.wait(), 30)
                second = asyncio.create_task(submit(1))
                await asyncio.wait_for(entered.wait(), 30)
                async with h.factory() as observer:
                    async with asyncio.timeout(15):
                        while not await observer.scalar(text(
                            "SELECT cardinality(pg_catalog.pg_blocking_pids(:pid)) > 0"
                        ), {"pid": contender_pid[0]}):
                            await asyncio.sleep(0.02)
                assert not second.done()
                release.set()
                winner, loser = await asyncio.wait_for(
                    asyncio.gather(first, second, return_exceptions=True), 90)
            finally:
                release.set()
                loser_done.set()
                for pending in (first, second):
                    if pending is not None and not pending.done():
                        pending.cancel()
                await asyncio.gather(*(pending for pending in (first, second) if pending is not None),
                                     return_exceptions=True)
        assert not isinstance(winner, BaseException), winner
        assert isinstance(loser, TaskSubmissionContextUnavailable), loser
        assert str(loser) == "task_submission_operation_in_progress"
        assert body_reads == [0]
        assert all(not errors for _, _, errors in commands)
        assert winner["status"] == "accepted" and winner["replayed"] is False
        async with h.factory() as session:
            assert await session.scalar(select(func.count()).select_from(SubmissionIntakeOperation).where(
                SubmissionIntakeOperation.idempotency_key.in_([str(key) for key in keys]))) == 1
            operation = await session.get(SubmissionIntakeOperation, winner["operation_id"])
            assert operation.idempotency_key == str(keys[0]) and operation.state == "finalization_pending"
            charge = await session.get(SubmissionSourceCharge, operation.id)
            assert charge.state == "sealed" and charge.accounted_bytes == len(first_data)
        submission_id = await finalize_retained_intake(h.factory, SimpleNamespace(
            operation_id=UUID(winner["operation_id"]), store=h.store.wrapped,
            namespace=h.namespace, settings=h.settings))
        async with h.factory() as session:
            dispatch = await session.get(SubmissionDispatch, submission_id)
            assert dispatch.submission_version == 2 and dispatch.checker_remediation_manifest_id == source_id
            assert await session.scalar(select(func.count()).select_from(Submission).where(
                Submission.task_id == str(h.request.task_id), Submission.version == 2)) == 1
        before = await _creation_snapshot(h)
        assert await submit(0) == dict(winner, replayed=True)
        assert await _creation_snapshot(h) == before


async def test_late_outbox_insert_failure_rolls_back_and_accepted_retry_succeeds(
    tmp_path, isolated_database_env,
):
    """Real failed POST INSERT leaves T4 custody; the same event retries real T5."""
    from datetime import timedelta
    from uuid import UUID
    from app.adapters.artifacts import submission_finalization_handler
    from app.adapters.auth import outbox_dispatch_authorization
    from app.adapters.outbox import outbox_delivery
    from app.modules.artifacts.api.submission_intake import SubmissionIntakeMetadata
    from app.modules.artifacts.intake.models import SubmissionIntakeOperation, SubmissionSourceCharge
    from app.modules.outbox.api import DeliveryOptions
    from app.modules.outbox.registry import HandlerRegistry
    from tests.artifacts.test_submission_pre_source import _source_runtime
    from tests.post_submit_materialization_helpers import _submit_current_source
    from tests.retained_material_fixtures import _foreground
    from tests.selected_predecessor_fixtures import _snapshot as artifact_snapshot

    async with remediation_source(tmp_path, isolated_database_env) as h:
        source_id = await _fixture_revision_context(h)
        data = revision_archive(h.data)
        runtime_root = tmp_path / "revision-runtime"
        runtime_root.mkdir()
        runtime, errors = _source_runtime(data, runtime_root, "completed")
        command = _foreground(h.factory, h.actor_context, h.namespace, h.store.wrapped, runtime)
        metadata = SubmissionIntakeMetadata(
            task_id=h.request.task_id, assignment_id=h.request.assignment_id,
            predecessor_submission_id=h.created.submission_id,
            revision_preparation_id=UUID(str(h.revision_preparation_id)),
            revision_preparation_sha256=h.revision_preparation_sha256,
            summary=h.creation_request.summary,
            contributor_attestation=h.creation_request.contributor_attestation,
        )
        receipt = await _submit_current_source(h.factory, h.actor_context, command, metadata, data)
        assert receipt["status"] == "accepted" and not errors, errors
        operation_id = receipt["operation_id"]
        async with h.factory() as session:
            operation = await session.get(SubmissionIntakeOperation, operation_id)
            event_id, project_id = UUID(operation.finalization_event_id), UUID(operation.project_id)
            event_ids = set((await session.execute(select(OutboxEvent.event_id))).scalars())
        before = await _creation_snapshot(h)
        artifacts_before = await artifact_snapshot(h)
        handler = submission_finalization_handler(sessions=h.factory, settings=h.settings,
            store=h.store.wrapped, lease_duration=timedelta(seconds=40))
        failures = []
        async def observed(envelope):
            try:
                return await handler(envelope)
            except Exception as error:
                failures.append(error)
                raise
        event_type = "SubmissionFinalizationRequested"
        delivery = outbox_delivery(h.factory, authorization_factory=outbox_dispatch_authorization,
            registry=HandlerRegistry([(event_type, 1, observed)], replay_safe=frozenset({(event_type, 1)})),
            options=DeliveryOptions(lease_seconds=60, handler_timeout_seconds=50,
                                    retry_base_seconds=1, retry_cap_seconds=1))
        async with h.factory() as session, session.begin():
            await session.execute(
                text("CREATE SEQUENCE public.test_replacement_outbox_attempt")
            )
            await session.execute(
                text(
                    """
                    CREATE FUNCTION public.test_replacement_outbox_failure()
                    RETURNS trigger LANGUAGE plpgsql AS $$
                    BEGIN
                      PERFORM nextval('public.test_replacement_outbox_attempt');
                      RAISE EXCEPTION 'controlled replacement outbox insert failure'
                        USING ERRCODE='23514';
                    END $$
                    """
                )
            )
            await session.execute(
                text(
                    """
                    CREATE TRIGGER test_replacement_outbox_failure
                    BEFORE INSERT ON public.outbox_events
                    FOR EACH ROW
                    WHEN (NEW.event_type='PostSubmissionEvaluationRequested')
                    EXECUTE FUNCTION public.test_replacement_outbox_failure()
                    """
                )
            )

        try:
            assert await delivery.deliver(event_id, project_id, "failed-revision-worker") is not None
            assert len(failures) == 1 and isinstance(failures[0], OutboxPersistenceError)
            assert str(failures[0]) == "outbox_persistence_failed"
            # OUTBOX deliberately suppresses provider/database details; the sequence
            # below independently proves the real SQL fault executed.
            assert failures[0].__cause__ is None
            async with h.factory() as session:
                assert (await session.execute(text(
                    "SELECT last_value,is_called FROM public.test_replacement_outbox_attempt"
                ))).one() == (1, True)
                operation = await session.get(SubmissionIntakeOperation, operation_id)
                assert operation.state == "finalization_pending" and operation.acceptance_receipt == receipt
                assert operation.finalized_submission_id is None
                charge = await session.get(SubmissionSourceCharge, operation_id)
                assert charge.state == "sealed" and charge.accounted_bytes > 0
                event = await session.get(OutboxEvent, event_id)
                assert event.delivery_state == "retryable" and event.attempt_count == 1
                assert set((await session.execute(select(OutboxEvent.event_id))).scalars()) == event_ids
                ready_at = max(event.next_attempt_at, operation.continuation_expires_at)
                remaining = (ready_at - await session.scalar(select(func.clock_timestamp()))).total_seconds()
            after = await _creation_snapshot(h)
            # OUTBOX delivery state and continuation authority legitimately advance;
            # product/ART/checker rows, human/binding allows and TASK remain unchanged.
            assert after[:8] == before[:8]
            assert await artifact_snapshot(h) == artifacts_before
            assert after[9] == before[9]
        finally:
            async with h.factory() as session, session.begin():
                await session.execute(
                    text(
                        "DROP TRIGGER IF EXISTS test_replacement_outbox_failure "
                        "ON public.outbox_events"
                    )
                )
                await session.execute(
                    text(
                        "DROP FUNCTION IF EXISTS "
                        "public.test_replacement_outbox_failure()"
                    )
                )
                await session.execute(
                    text(
                        "DROP SEQUENCE IF EXISTS "
                        "public.test_replacement_outbox_attempt"
                    )
                )

        await asyncio.sleep(max(0, remaining) + 0.05)
        assert await delivery.deliver(event_id, project_id, "retry-revision-worker") is not None
        assert len(failures) == 1
        async with h.factory() as session:
            operation = await session.get(SubmissionIntakeOperation, operation_id)
            assert operation.state == "finalized" and operation.continuation_generation == 2
            event = await session.get(OutboxEvent, event_id)
            assert event.delivery_state == "acknowledged" and event.attempt_count == 2
            dispatch = await session.get(SubmissionDispatch, operation.finalized_submission_id)
            assert dispatch.submission_version == 2 and dispatch.checker_remediation_manifest_id == source_id
            submission = await session.get(Submission, operation.finalized_submission_id)
            assert submission.supersedes_submission_id == str(h.created.submission_id)
            admission = await session.get(SubmissionBundleAdmission, operation.finalized_admission_id)
            assert admission.status == "consumed" and admission.source_operation_id == operation_id
            assert await session.scalar(select(func.count()).select_from(Submission).where(
                Submission.task_id == str(h.request.task_id), Submission.version == 2)) == 1
            assert set((await session.execute(select(OutboxEvent.event_id))).scalars()) == event_ids | {UUID(str(dispatch.evaluation_event_id))}
            assert await session.scalar(text(
                "SELECT public.submission_dispatch_valid(d) FROM public.submission_dispatches d WHERE d.submission_id=:id"
            ), {"id": dispatch.submission_id}) is True
