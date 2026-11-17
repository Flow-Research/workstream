"""T5 failures preserve accepted custody and roll back every finalization owner."""

import pytest
from sqlalchemy import select, func, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.modules.authorization.prepared import PreparedAuthorizationUnsupported
from app.modules.artifacts.models import SubmissionBundleAdmission, SubmissionBindingReceipt, ArtifactBinding
from app.modules.artifacts.authorization import PreparedSubmissionFinalizationAuthorization
from app.modules.artifacts.intake.models import SubmissionIntakeOperation
from app.modules.artifacts.submission_bindings import SubmissionAdmissionConsumptionService
from app.modules.checkers.api.execution import CheckerExecutionUnavailable, REQUEST_EVENT
from app.modules.checkers.execution_coordination import EvaluationCoordinator
from app.modules.checkers.models import CheckerRun
from app.modules.outbox.models import OutboxEvent
from app.modules.outbox.service import OutboxService
from app.modules.tasks.models import Submission, SubmissionDispatch, AuditEvent, WorkstreamTask
from app.modules.tasks.submission_composition import TaskSubmissionCreationService
from tests.post_submit_materialization_helpers import material_fixture


class ParticipantFailure(RuntimeError):
    pass


async def assert_accepted_without_finalization(database_url):
    engine = create_async_engine(database_url)
    try:
        async with async_sessionmaker(engine)() as session:
            for model in (Submission, SubmissionDispatch, SubmissionBundleAdmission,
                          SubmissionBindingReceipt, ArtifactBinding, CheckerRun):
                assert await session.scalar(select(func.count()).select_from(model)) == 0
            assert await session.scalar(select(WorkstreamTask.status)) == "evaluation_pending"
            operation = (await session.scalars(select(SubmissionIntakeOperation))).one()
            assert operation.state == "finalization_pending" and operation.acceptance_receipt is not None
            assert operation.finalized_submission_id is None
            assert await session.scalar(select(func.count()).select_from(OutboxEvent).where(
                OutboxEvent.event_type == "SubmissionFinalizationRequested")) == 1
            assert await session.scalar(select(func.count()).select_from(OutboxEvent).where(
                OutboxEvent.event_type == REQUEST_EVENT)) == 0
            assert await session.scalar(select(func.count()).select_from(AuditEvent).where(
                AuditEvent.action_id == "submission.create")) == 1
    finally:
        await engine.dispose()


@pytest.mark.parametrize("owner,method,stored", [
    (SubmissionAdmissionConsumptionService, "consume", SubmissionBindingReceipt),
    (PreparedSubmissionFinalizationAuthorization, "consume", AuditEvent),
    (EvaluationCoordinator, "reserve_current_evaluation", CheckerRun),
    (OutboxService, "append", OutboxEvent),
    (TaskSubmissionCreationService, "create_accepted", SubmissionDispatch),
])
async def test_participant_failure_rolls_back_actual_staged_rows(
    tmp_path, isolated_database_env, monkeypatch, owner, method, stored,
):
    original = getattr(owner, method)
    observed = []

    async def fail_after_write(self, *args, **kwargs):
        result = await original(self, *args, **kwargs)
        if owner is OutboxService and args[0].event_type != REQUEST_EVENT:
            return result
        if owner is PreparedSubmissionFinalizationAuthorization and kwargs["facts"].phase != "commit":
            return result
        session = self._repository._session if owner is OutboxService else self._session
        query = select(func.count()).select_from(stored)
        if stored is AuditEvent:
            query = query.where(AuditEvent.action_id == "artifact.submission.finalize")
        elif stored is OutboxEvent:
            query = query.where(OutboxEvent.event_type == REQUEST_EVENT)
        assert await session.scalar(query) == (2 if stored is AuditEvent else 1)
        observed.append(result)
        raise ParticipantFailure("after real participant write")

    monkeypatch.setattr(owner, method, fail_after_write)
    with pytest.raises(AssertionError, match="expected successful retained source finalization") as error:
        async with material_fixture(tmp_path, isolated_database_env):
            pytest.fail("partial finalization committed")
    assert isinstance(error.value.__cause__, ParticipantFailure)
    assert len(observed) == 1
    await assert_accepted_without_finalization(isolated_database_env)


async def test_raw_savepoint_cannot_release_creation_custody(tmp_path, isolated_database_env, monkeypatch):
    original = TaskSubmissionCreationService.create_accepted
    observed = []

    async def inside_raw_savepoint(self, request, **kwargs):
        await self._session.execute(text("SAVEPOINT caller_savepoint"))
        assert self._session.in_nested_transaction() is False
        observed.append(True)
        return await original(self, request, **kwargs)

    monkeypatch.setattr(TaskSubmissionCreationService, "create_accepted", inside_raw_savepoint)
    with pytest.raises(AssertionError, match="expected successful retained source finalization") as error:
        async with material_fixture(tmp_path, isolated_database_env):
            pytest.fail("creation accepted an unmanaged savepoint")
    assert isinstance(error.value.__cause__, CheckerExecutionUnavailable)
    assert "checker_caller_transaction_required" in str(error.value.__cause__)
    assert observed == [True]
    await assert_accepted_without_finalization(isolated_database_env)


async def test_revoked_binding_identity_preserves_accepted_custody(tmp_path, isolated_database_env):
    from tests.post_submit_materialization_helpers import _material_fixture, _submit_current_source, _read_current_request

    async def revoke_after_acceptance(factory, context, command, metadata, data):
        receipt = await _submit_current_source(factory, context, command, metadata, data)
        async with factory.begin() as session:
            await session.execute(text("""UPDATE public.actor_identity_links SET status='revoked',
                revoked_by='dispatch-test', revoked_at=clock_timestamp(), revoked_reason='Withdraw binding authority'
                WHERE actor_profile_id IN (SELECT id FROM public.actor_profiles
                    WHERE service_identity='workstream.artifact.binding')"""))
        return receipt

    with pytest.raises(AssertionError, match="expected successful retained source finalization") as error:
        async with _material_fixture(tmp_path, isolated_database_env,
                                     submit_source=revoke_after_acceptance, read_request=_read_current_request):
            pytest.fail("revoked binding service created a Submission")
    assert isinstance(error.value.__cause__, PreparedAuthorizationUnsupported)
    await assert_accepted_without_finalization(isolated_database_env)
