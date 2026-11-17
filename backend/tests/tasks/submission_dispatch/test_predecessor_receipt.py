"""Deferred accepted-revision receipt rejects a genuine foreign routed cause."""

from uuid import UUID

import pytest
from sqlalchemy import event, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.artifacts.api.submission_intake import SubmissionIntakeMetadata
from app.modules.artifacts.intake.models import SubmissionIntakeOperation, SubmissionSourceCharge
from app.modules.tasks.models import Submission, SubmissionDispatch, WorkstreamTask
from app.modules.checkers.models import CheckerRun
from app.modules.outbox.models import OutboxEvent
from app.modules.tasks.submission_composition import TaskSubmissionCreationService
from tests.post_submit_materialization_helpers import create_source_submission, _submit_current_source
from tests.tasks.post_submit_routing.remediation_support import remediation_source, no_economic_effects
from tests.tasks.post_submit_routing.support import revision_archive
from tests.test_submission_predecessor_custody import _fixture_revision_context
from tests.selected_predecessor_fixtures import _snapshot


@pytest.mark.parametrize("foreign_cause", [False, True], ids=["valid", "foreign-manifest"])
async def test_deferred_dispatch_checks_accepted_successor_cause(
    tmp_path, isolated_database_env, monkeypatch, foreign_cause,
):
    """Only the foreign dispatch cause fails after otherwise complete real T5 staging."""
    async with remediation_source(tmp_path / "local", isolated_database_env) as local:
        async with remediation_source(
            tmp_path / "foreign", isolated_database_env,
            provision_services=False, storage_settings=local.settings,
        ) as foreign:
            local_source = await _fixture_revision_context(local)
            foreign_source = await _fixture_revision_context(foreign)
            assert local_source != foreign_source
            metadata = SubmissionIntakeMetadata(
                task_id=local.request.task_id, assignment_id=local.request.assignment_id,
                predecessor_submission_id=local.created.submission_id,
                revision_preparation_id=UUID(str(local.revision_preparation_id)),
                revision_preparation_sha256=local.revision_preparation_sha256,
                summary=local.creation_request.summary,
                contributor_attestation=local.creation_request.contributor_attestation,
            )
            accepted, staged, checked = [], [], []
            original_create, original_commit = TaskSubmissionCreationService.create_accepted, AsyncSession.commit

            async def observe_acceptance(factory, context, command, selected, data):
                receipt = await _submit_current_source(factory, context, command, selected, data)
                accepted.append((receipt, await _snapshot(local)))
                return receipt

            def foreign_dispatch_cause(_mapper, _connection, dispatch):
                assert dispatch.task_id == str(local.request.task_id)
                assert dispatch.checker_remediation_manifest_id == local_source
                if foreign_cause:
                    dispatch.checker_remediation_manifest_id = foreign_source

            async def observe_creation(service, selected, **kwargs):
                result, decision = await original_create(service, selected, **kwargs)
                staged.append(result)
                service._session.info["predecessor_receipt_test"] = result
                return result, decision

            async def check_complete_commit(session):
                result = session.info.pop("predecessor_receipt_test", None)
                if result is not None:
                    operation = await session.scalar(select(SubmissionIntakeOperation).where(
                        SubmissionIntakeOperation.finalized_submission_id == str(result.submission_id)))
                    assert operation is not None and operation.state == "finalized"
                    assert await session.scalar(text(
                        "SELECT count(*) FROM public.submission_dispatches WHERE submission_id=:id"
                    ), {"id": result.submission_id}) == 1
                    checked.append(result.submission_id)
                    await session.execute(text("SET CONSTRAINTS submission_dispatch_complete IMMEDIATE"))
                return await original_commit(session)

            monkeypatch.setattr(TaskSubmissionCreationService, "create_accepted", observe_creation)
            monkeypatch.setattr(AsyncSession, "commit", check_complete_commit)
            event.listen(SubmissionDispatch, "before_insert", foreign_dispatch_cause)
            try:
                async def submit():
                    return await create_source_submission(
                        local.factory, local.actor_context, local.store.wrapped, local.namespace,
                        local.settings, metadata, revision_archive(local.data), submit_source=observe_acceptance)
                if foreign_cause:
                    with pytest.raises(AssertionError, match="expected successful retained source finalization") as denied:
                        await submit()
                    error = denied.value.__cause__
                    assert isinstance(error, IntegrityError)
                    assert error.orig.sqlstate == "23514"
                    assert "replacement dispatch evaluation is not current" in str(error)
                else:
                    result = await submit()
                    assert result.submission_version == 2
            finally:
                event.remove(SubmissionDispatch, "before_insert", foreign_dispatch_cause)
            assert len(accepted) == len(staged) == len(checked) == 1
            assert checked[0] == staged[0].submission_id
            receipt, before = accepted[0]
            async with local.factory() as session:
                operation = await session.get(SubmissionIntakeOperation, receipt["operation_id"])
                charge = await session.get(SubmissionSourceCharge, operation.id)
                assert charge.state == "sealed" and charge.accounted_bytes > 0
                task = await session.get(WorkstreamTask, str(local.request.task_id))
                assert task.status == "evaluation_pending"
                if foreign_cause:
                    assert await _snapshot(local) == before
                    assert operation.state == "finalization_pending" and operation.acceptance_receipt == receipt
                    assert operation.finalized_submission_id is None
                    assert task.active_submission_operation_id == operation.id
                    assert await session.get(SubmissionDispatch, str(staged[0].submission_id)) is None
                    assert await session.get(Submission, str(staged[0].submission_id)) is None
                    assert await session.get(CheckerRun, str(staged[0].evaluation_attempt_id)) is None
                    assert await session.get(OutboxEvent, staged[0].evaluation_event_id) is None
                    finalization = await session.get(OutboxEvent, UUID(operation.finalization_event_id))
                    assert finalization.event_type == "SubmissionFinalizationRequested"
                    assert finalization.payload["operation_id"] == operation.id
                else:
                    assert operation.state == "finalized"
                    assert operation.finalized_submission_id == str(result.submission_id)
                    dispatch = await session.get(SubmissionDispatch, str(result.submission_id))
                    assert dispatch.checker_remediation_manifest_id == local_source
                    assert task.active_submission_operation_id is None
                await no_economic_effects(session)
