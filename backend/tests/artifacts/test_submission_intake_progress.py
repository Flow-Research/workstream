"""Exact finalized source custody and public progress through governed routing."""
from types import SimpleNamespace

import pytest

from app.core.identifiers import new_record_id
from app.modules.artifacts.intake.models import SubmissionIntakeOperation
from tests.test_artifact_admission import _settings
from tests.artifacts.test_submission_intake_admission import admission_intake as admission_intake
from tests.authentication.fixtures import (
    auth_database_env as auth_database_env,
    clear_settings_cache as clear_settings_cache,
    rsa_signing_material as rsa_signing_material,
)
from tests.authorization.admin_access.fixtures import (
    signed_access as signed_access,
    admin_access as admin_access,
)
from datetime import timedelta
from sqlalchemy import text
from app.adapters.artifacts import submission_admission_consumption_port
from app.adapters.checkers import selected_pre_submit_coordinator
from app.adapters.outbox import outbox_append
from app.adapters.tasks import accepted_submission_creation_service
from app.modules.outbox.api import OutboxAppendInput
from app.modules.actors.api import ServiceIdentity
from app.modules.artifacts.authorization import PreparedSubmissionFinalizationAuthorization
from app.modules.artifacts.intake.finalization import AcceptedSubmissionFinalization
from tests.artifact_store_helpers import initialize_local_store
from tests.artifacts.intake_acceptance_support import completed_source
from tests.checkers.execution.support import provision_post_submit_service
from app.adapters.tasks import submission_history_repository
from app.modules.tasks.api.submission_history import SubmissionOperationAssociationUnavailable
from app.adapters.checkers import evaluation_coordinator
from app.modules.checkers.api.execution import CheckerExecutionUnavailable
from sqlalchemy.exc import IntegrityError
from tests.artifacts.intake_post_support import exercise_source_post
from tests.checkers.execution.support import ControlledSelectedExecution
from tests.artifacts.intake_post_support import leave_expired_finalizer_claim
from app.modules.artifacts.intake.progress import evaluation_delivery_progress
from app.adapters.outbox import finalized_unknown_deliveries
from app.adapters.checkers import checker_retry_service
from tests.checkers.execution.test_checker_retry import _operator_for, _command
from app.adapters.auth import outbox_dispatch_authorization
from app.adapters.outbox import outbox_delivery
from app.adapters.tasks import evaluation_completion_handler
from app.modules.checkers.api.execution import COMPLETION_EVENT
from app.modules.outbox.api import DeliveryOptions
from app.modules.outbox.registry import HandlerRegistry
from tests.authorization.post_submit_routing.support import provision_router
from tests.tasks.evaluation_delivery.support import outcome as delivery_outcome
from app.interfaces.artifacts import ArtifactObjectMissingError


async def _assert_retained_custody(f, owner, request, result, expired_claim):
    async with f.factory() as session:
        row = await session.get(SubmissionIntakeOperation, str(owner.operation_id))
        assert row.state == "finalized" and row.finalized_submission_id == str(result.submission_id)
        assert row.continuation_generation == (2 if expired_claim else 1)
        task = (await session.execute(text("SELECT status, active_submission_operation_id "
            "FROM workstream_tasks WHERE id=:id"), {"id": f.task})).one()
        assert task.status == "evaluation_pending" and task.active_submission_operation_id is None
        admission = (await session.execute(text("SELECT source_operation_id, durable_intent_id, put_attempt_id, "
            "verification_receipt_id FROM submission_bundle_admissions WHERE id=:id"),
            {"id": result.admission_id})).one()
        assert admission.source_operation_id == owner.operation_id
        assert admission.durable_intent_id is admission.put_attempt_id is admission.verification_receipt_id is None
        replica = (await session.execute(text("SELECT provider_object_ref FROM artifact_replicas "
            "WHERE source_operation_id=:id"), {"id": owner.operation_id})).one()
        assert replica.provider_object_ref == request.source.location.object_ref
        for table in ("submissions", "submission_dispatches", "checker_runs"):
            assert await session.scalar(text(f"SELECT count(*) FROM {table} WHERE task_id=:id"), {"id": f.task}) == 1
        assert await session.scalar(text("SELECT count(*) FROM outbox_events WHERE project_id=:id "
            "AND event_type='PostSubmissionEvaluationRequested'"), {"id": f.project}) == 1
        assert await session.scalar(text("SELECT count(*) FROM submission_source_charges WHERE operation_id=:id"),
            {"id": owner.operation_id}) == 1
    # Removing retained provenance must fail at commit even when all other
    # replica coordinates remain unchanged.
    evaluation_selectors = dict(project_id=f.project, task_id=f.task,
                                submission_id=result.submission_id,
                                original_request_id=result.evaluation_request_id)
    async with f.factory.begin() as session:
        coordinator = evaluation_coordinator(session)
        queued = await coordinator.read_current_progress(**evaluation_selectors)
        assert queued.status == "queued" and not queued.live_worker_lease
        assert queued.retry_event_id is queued.completion_event_id is None
        for field in evaluation_selectors:
            with pytest.raises(CheckerExecutionUnavailable):
                await coordinator.read_current_progress(**(evaluation_selectors | {field: new_record_id()}))
    selectors = dict(project_id=f.project, task_id=f.task, assignment_id=request.assignment_id,
                     contributor_id=request.actor_profile_id, submission_id=result.submission_id,
                     admission_id=result.admission_id)
    async with f.factory.begin() as session:
        history = submission_history_repository(session)
        outcome = await history.read_operation_outcome(**selectors)
        assert outcome.submission_id == result.submission_id
        assert outcome.submission_version == result.submission_version
        assert outcome.evaluation_request_id == result.evaluation_request_id
        assert outcome.status == "evaluation_pending"
        pending = await evaluation_delivery_progress(
            outcome.evaluation_event_id, OutboxAppendInput.model_validate_json(outcome.evaluation_event_json), queued,
            outbox_append(session), finalized_unknown_deliveries(session),
        )
        assert pending.state == "pending"
        for field in selectors:
            with pytest.raises(SubmissionOperationAssociationUnavailable):
                await history.read_operation_outcome(**(selectors | {field: new_record_id()}))
    async with f.factory() as session:
        with pytest.raises(IntegrityError, match="retained source ownership is immutable"):
            async with session.begin():
                await session.execute(text("UPDATE artifact_replicas SET source_operation_id=NULL "
                    "WHERE source_operation_id=:id"), {"id": owner.operation_id})
    substitutions = (
        ("UPDATE artifact_contents SET sha256='sha256:' || repeat('f',64) WHERE id=:id",
         result.artifact_content_id, "accepted source content is immutable"),
        ("UPDATE artifact_contents SET byte_count=byte_count+1 WHERE id=:id",
         result.artifact_content_id, "accepted source content is immutable"),
        ("UPDATE artifact_contents SET media_type='application/octet-stream' WHERE id=:id",
         result.artifact_content_id, "accepted source content is immutable"),
        ("UPDATE artifact_replicas SET adapter='substituted' WHERE source_operation_id=:id",
         owner.operation_id, "source admission provenance mismatch"),
    )
    for statement, identity, message in substitutions:
        async with f.factory() as session:
            with pytest.raises(IntegrityError, match=message):
                async with session.begin():
                    await session.execute(text(statement), {"id": identity})
    return SimpleNamespace(queued=queued, outcome=outcome,
                           selectors=selectors, evaluation_selectors=evaluation_selectors)


@pytest.mark.parametrize("expired_claim,post_failure", [(False, False), (True, False), (False, True)])
async def test_t5_finalizes_same_source_with_one_submission_and_post_dispatch(admission_intake, tmp_path, monkeypatch, expired_claim, post_failure):

    f = admission_intake
    owner, request, terminal = await completed_source(f, tmp_path)
    accepted = await f.admission.accept(owner, request, terminal.terminal_digest,
        checkers=selected_pre_submit_coordinator, outbox=outbox_append)
    await provision_post_submit_service(f.factory, ServiceIdentity.ARTIFACT_BINDING)
    store = initialize_local_store(root=tmp_path / "durable", buffer_bytes=256 * 1024)
    def submissions(session):
        return accepted_submission_creation_service(session, settings=_settings(tmp_path),
            admissions=submission_admission_consumption_port(session,
                request_id=new_record_id(), correlation_id=owner.operation_id))
    finalizer = AcceptedSubmissionFinalization(
        f.factory, tasks=f.admission._tasks, submissions=submissions,
        checkers=selected_pre_submit_coordinator, store=store, lease_duration=timedelta(seconds=60),
        authorization=lambda session: PreparedSubmissionFinalizationAuthorization(
            session, request_id=new_record_id(), correlation_id=owner.operation_id),
    )
    try:
        if expired_claim:
            await leave_expired_finalizer_claim(f, finalizer, owner.operation_id)
        result = await finalizer.run(owner.operation_id)
        assert await finalizer.run(owner.operation_id) == result
        assert await f.admission.accept(owner, request, terminal.terminal_digest,
            checkers=selected_pre_submit_coordinator, outbox=outbox_append) == dict(accepted, replayed=True)
        async def public_progress(stage, evaluation_request_id, *, stalled=False, governed=False):
            response = await f.access.signed.client.get(
                f"/api/v1/tasks/{f.task}/submission-operations", headers=f.access.target.headers,
                params={"operation_id": str(owner.operation_id)},
            )
            assert response.status_code == 200, response.text
            observed = response.json()
            assert observed["operation_state"] == "finalized"
            assert observed["submission_id"] == str(result.submission_id)
            assert observed["submission_version"] == result.submission_version
            assert observed["evaluation_request_id"] == str(evaluation_request_id)
            assert observed["processing_stage"] == stage
            assert observed["operationally_stalled"] is stalled
            assert observed["next_action"] == ("inspect_governed_outcome" if governed else "wait")
            return observed

        await public_progress("evaluation_pending", result.evaluation_request_id)
        observed = await _assert_retained_custody(f, owner, request, result, expired_claim)
        queued, outcome = observed.queued, observed.outcome
        selectors, evaluation_selectors = observed.selectors, observed.evaluation_selectors
        running_observations = []
        original_execute = ControlledSelectedExecution.execute
        async def observe_running(runtime, execution_request, grant):
            async with f.factory.begin() as session:
                running = await evaluation_coordinator(session).read_current_progress(**evaluation_selectors)
                assert running.status == "running" and running.live_worker_lease
                assert running.completion_event_id is None
                running_observations.append(running)
            await public_progress("evaluation_running", result.evaluation_request_id)
            return await original_execute(runtime, execution_request, grant)
        with monkeypatch.context() as patch:
            patch.setattr(ControlledSelectedExecution, "execute", observe_running)
            if post_failure:
                def missing_source(*_args, **_kwargs):
                    raise ArtifactObjectMissingError("controlled source unavailable")
                patch.setattr(type(store), "open_source", missing_source)
            await exercise_source_post(f, result, store, request.source, tmp_path, missing=post_failure)
        assert len(running_observations) == (0 if post_failure else 1)
        async with f.factory.begin() as session:
            # Completed checker evidence alone does not change the governed attempt.
            after_post = await submission_history_repository(session).read_operation_outcome(**selectors)
            assert after_post == outcome
            completed = await evaluation_coordinator(session).read_current_progress(**evaluation_selectors)
            assert completed.status == ("infrastructure_failed" if post_failure else "completed")
            assert not completed.live_worker_lease and completed.current == queued.current
            assert (completed.completion_event_id is None) is post_failure
            assert completed.retry_event_id is None
            if not post_failure:
                pending_completion = await evaluation_delivery_progress(
                    completed.completion_event_id, OutboxAppendInput.model_validate_json(completed.delivery_event_json), completed,
                    outbox_append(session), finalized_unknown_deliveries(session),
                )
                assert pending_completion.state == "pending"
        await public_progress("operationally_stalled" if post_failure else "evaluation_pending",
                              result.evaluation_request_id, stalled=post_failure)
        if post_failure:
            harness = SimpleNamespace(factory=f.factory, request=queued.current.request, created=result)
            operator = await _operator_for(harness)
            async with f.factory.begin() as session:
                retry = await checker_retry_service(session, operator).retry(_command(harness, operator))
            async with f.factory.begin() as session:
                retrying = await evaluation_coordinator(session).read_current_progress(**evaluation_selectors)
                assert retrying.status == "queued" and not retrying.live_worker_lease
                assert retrying.current.reservation.attempt_id == retry.successor.run_id
                assert retrying.retry_event_id == retry.successor.event_id
                assert retrying.completion_event_id is None
                pending_retry = await evaluation_delivery_progress(
                    retrying.retry_event_id, OutboxAppendInput.model_validate_json(retrying.delivery_event_json), retrying,
                    outbox_append(session), finalized_unknown_deliveries(session),
                )
                assert pending_retry.state == "pending"
            await public_progress("evaluation_pending", retrying.current.request.evaluation_request_id)
        else:

            await provision_post_submit_service(f.factory, ServiceIdentity.OUTBOX_DISPATCHER)
            await provision_router(f.factory)
            dispatcher = outbox_delivery(
                f.factory, authorization_factory=outbox_dispatch_authorization,
                registry=HandlerRegistry([(COMPLETION_EVENT, 1,
                    evaluation_completion_handler(sessions=f.factory))]),
                options=DeliveryOptions(),
            )
            delivered = await dispatcher.deliver(
                completed.completion_event_id, f.project, "source-progress-governed-outcome")
            assert delivery_outcome(delivered)["delivery_state"] == "acknowledged", delivery_outcome(delivered)
            async with f.factory.begin() as session:
                governed = await submission_history_repository(session).read_operation_outcome(**selectors)
                assert governed.status == "review_pending"
            await public_progress("review_pending", result.evaluation_request_id, governed=True)

    finally:
        store.close()

