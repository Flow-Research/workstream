"""Accepted T5 dispatch custody, exact retained reads, and atomic rollback."""

import pytest
from sqlalchemy import select, func, text

from app.adapters.artifacts import submission_admission_consumption_port
from app.adapters.tasks import accepted_submission_creation_service
from app.core.identifiers import new_record_id
from app.modules.checkers.models import CheckerRun
from app.modules.outbox.models import OutboxEvent
from app.modules.tasks.models import AuditEvent, SubmissionDispatch, WorkstreamTask
from tests.post_submit_materialization_helpers import material_fixture


def _accepted_tasks(session, settings):
    return accepted_submission_creation_service(
        session, settings=settings,
        admissions=submission_admission_consumption_port(
            session, request_id=new_record_id(), correlation_id=new_record_id(),
        ),
    )


def _receipt_key(result):
    return dict(submission_id=result.submission_id, admission_id=result.admission_id,
                creation_decision_id=result.creation_decision_id)


async def test_creation_commits_exact_dispatch_and_retained_read(tmp_path, isolated_database_env):
    """T5 commits exact POST custody; its internal retained read creates nothing."""
    async with material_fixture(tmp_path, isolated_database_env) as h:
        result = h.created
        async with h.factory() as session:
            receipt = await session.get(SubmissionDispatch, result.submission_id)
            assert receipt is not None and receipt.result() == result
            assert (await session.get(WorkstreamTask, str(h.request.task_id))).status == "evaluation_pending"
            run = await session.get(CheckerRun, str(result.evaluation_attempt_id))
            assert run.evaluation_request_id == str(result.evaluation_request_id)
            assert run.request_digest == result.evaluation_request_digest == h.request.request_sha256
            assert run.result_id == str(result.evaluation_result_id)
            assert run.evaluation_generation == 1 and run.status == "queued"
            event = await session.get(OutboxEvent, result.evaluation_event_id)
            assert event.payload["request_id"] == str(result.evaluation_request_id)
            assert event.payload["creation_decision_id"] == str(result.creation_decision_id)
            assert event.payload["binding_decision_id"] == str(result.binding_decision_id)
            assert await session.scalar(text("SELECT public.submission_dispatch_valid(d) FROM public.submission_dispatches d WHERE submission_id=:id"), {"id": result.submission_id}) is True
            events = set((await session.execute(select(OutboxEvent.event_id, OutboxEvent.event_type))).all())
            assert len(events) == 2
            assert (result.evaluation_event_id, event.event_type) in events
            assert sum(kind == "SubmissionFinalizationRequested" for _, kind in events) == 1
            allows = await session.scalar(select(func.count()).select_from(AuditEvent).where(
                AuditEvent.action_id.in_(["submission.create", "artifact.submission.binding.create"]),
            ))
            assert allows == 2
        async with h.factory() as session:
            assert await _accepted_tasks(session, h.settings).read_finalized(**_receipt_key(result)) == result
        async with h.factory() as session:
            assert await session.scalar(select(func.count()).select_from(SubmissionDispatch)) == 1
            assert await session.scalar(select(func.count()).select_from(CheckerRun)) == 1
            assert set((await session.execute(select(OutboxEvent.event_id, OutboxEvent.event_type))).all()) == events
            assert await session.scalar(select(func.count()).select_from(AuditEvent).where(
                AuditEvent.action_id.in_(["submission.create", "artifact.submission.binding.create"]),
            )) == allows


async def test_changed_receipt_key_cannot_create_or_repair_dispatch(tmp_path, isolated_database_env, monkeypatch):
    """Every internal receipt identifier must match, without entering creation."""
    from app.modules.tasks.api import SubmissionCreationUnavailable
    from app.modules.checkers.execution_coordination import EvaluationCoordinator
    from app.modules.outbox.service import OutboxService

    async with material_fixture(tmp_path, isolated_database_env) as h:
        async with h.factory() as session:
            events = set((await session.execute(select(OutboxEvent.event_id))).scalars())
        async def forbidden(*args, **kwargs):
            pytest.fail("retained read entered a creation participant")
        monkeypatch.setattr(EvaluationCoordinator, "reserve_current_evaluation", forbidden)
        monkeypatch.setattr(OutboxService, "append", forbidden)
        key = _receipt_key(h.created)
        for field in key:
            async with h.factory() as session:
                with pytest.raises(SubmissionCreationUnavailable, match="finalized dispatch differs"):
                    await _accepted_tasks(session, h.settings).read_finalized(**{**key, field: new_record_id()})
        async with h.factory() as session:
            assert await session.scalar(select(func.count()).select_from(SubmissionDispatch)) == 1
            assert await session.scalar(select(func.count()).select_from(CheckerRun)) == 1
            assert set((await session.execute(select(OutboxEvent.event_id))).scalars()) == events
            assert await _accepted_tasks(session, h.settings).read_finalized(**key) == h.created


async def test_missing_dispatch_receipt_rejects_real_commit_and_rolls_back(tmp_path, isolated_database_env, monkeypatch):
    """A deferred T5 failure preserves accepted source custody for worker retry."""
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
    from sqlalchemy.exc import IntegrityError
    from app.modules.artifacts.models import SubmissionBundleAdmission, SubmissionBindingReceipt
    from app.modules.artifacts.intake.models import SubmissionIntakeOperation, SubmissionSourceCharge
    from app.modules.tasks.models import Submission
    from app.modules.tasks.submission_composition import TaskSubmissionCreationService

    add = AsyncSession.add
    create = TaskSubmissionCreationService.create_accepted
    staged = []

    def omit_only_dispatch(session, instance, **kwargs):
        if isinstance(instance, SubmissionDispatch):
            staged.append(instance)
            return
        return add(session, instance, **kwargs)

    async def observe_before_commit(service, request, **kwargs):
        result = await create(service, request, **kwargs)
        for model in (Submission, SubmissionBindingReceipt, CheckerRun):
            assert await service._session.scalar(select(func.count()).select_from(model)) == 1
        assert await service._session.scalar(select(func.count()).select_from(OutboxEvent)) == 2
        assert await service._session.scalar(select(SubmissionBundleAdmission.status)) == "consumed"
        return result

    monkeypatch.setattr(AsyncSession, "add", omit_only_dispatch)
    monkeypatch.setattr(TaskSubmissionCreationService, "create_accepted", observe_before_commit)
    with pytest.raises(AssertionError, match="expected successful retained source finalization") as failure:
        async with material_fixture(tmp_path, isolated_database_env):
            pytest.fail("incomplete creation committed")
    assert isinstance(failure.value.__cause__, IntegrityError)
    assert "submission finalization closure mismatch" in str(failure.value.__cause__)
    assert len(staged) == 1 and staged[0].evaluation_event_id is not None
    engine = create_async_engine(isolated_database_env)
    try:
        async with async_sessionmaker(engine)() as session:
            for model in (Submission, SubmissionDispatch, SubmissionBindingReceipt, SubmissionBundleAdmission, CheckerRun):
                assert await session.scalar(select(func.count()).select_from(model)) == 0
            operation = (await session.execute(select(SubmissionIntakeOperation))).scalar_one()
            assert operation.state == "finalization_pending"
            assert operation.finalized_submission_id is None
            assert operation.acceptance_receipt["status"] == "accepted"
            charge = await session.get(SubmissionSourceCharge, operation.id)
            assert charge.state == "sealed" and charge.accounted_bytes > 0
            task = await session.get(WorkstreamTask, operation.task_id)
            assert task.status == "evaluation_pending"
            assert task.active_submission_operation_id == operation.id
            event = (await session.execute(select(OutboxEvent))).scalar_one()
            assert str(event.event_id) == str(operation.finalization_event_id)
            assert event.event_type == "SubmissionFinalizationRequested"
            assert await session.scalar(select(func.count()).select_from(AuditEvent).where(
                AuditEvent.action_id == "artifact.submission.binding.create",
            )) == 0
            assert await session.scalar(select(func.count()).select_from(AuditEvent).where(
                AuditEvent.action_id == "submission.create",
            )) == 1
    finally:
        await engine.dispose()
