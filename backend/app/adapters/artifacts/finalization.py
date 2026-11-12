"""Compose accepted finalization through the existing TASK/ART/CHECKERS owners."""

from datetime import timedelta

from app.core.identifiers import new_record_id
from app.modules.artifacts.authorization import PreparedSubmissionFinalizationAuthorization
from app.modules.artifacts.intake.finalization import AcceptedSubmissionFinalization
from app.modules.artifacts.intake.finalization_delivery import (
    FinalizationInvocation, SubmissionFinalizationHandler,
)


def submission_finalization_handler(*, sessions, settings, store, lease_duration):
    from app.adapters.artifacts import submission_admission_consumption_port
    from app.adapters.checkers import selected_pre_submit_coordinator
    from app.adapters.outbox import committed_invocation_reader, outbox_invocation_fence
    from app.adapters.tasks import accepted_submission_creation_service, intake_task_custody_port

    def finalizer(envelope):
        operation_id = envelope.aggregate_id
        def submissions(session):
            return accepted_submission_creation_service(session, settings=settings,
                admissions=submission_admission_consumption_port(session,
                    request_id=new_record_id(), correlation_id=operation_id))
        return AcceptedSubmissionFinalization(
            sessions, tasks=intake_task_custody_port, submissions=submissions,
            checkers=selected_pre_submit_coordinator, store=store, lease_duration=lease_duration,
            authorization=lambda session: PreparedSubmissionFinalizationAuthorization(
                session, request_id=new_record_id(), correlation_id=operation_id),
            delivery=FinalizationInvocation(envelope, outbox_invocation_fence),
        )
    return SubmissionFinalizationHandler(
        observer=committed_invocation_reader(sessions), finalizer=finalizer,
    )


class _WorkerSourceObservation:
    """Initialize the provider only when an unfinalized operation needs metadata."""

    async def observe_sealed_source(self, source):
        from app.adapters.artifacts.internal_workers import (
            _artifact_internal_runtime, _artifact_worker_database,
            initialize_artifact_internal_runtime,
        )
        async with _artifact_worker_database():
            await initialize_artifact_internal_runtime()
            with _artifact_internal_runtime() as (store, _namespace):
                return await store.observe_sealed_source(source)


def worker_submission_finalization_handler(*, sessions, delivery_options):
    from app.core.config import get_settings
    return submission_finalization_handler(
        sessions=sessions, settings=get_settings(), store=_WorkerSourceObservation(),
        lease_duration=timedelta(seconds=delivery_options.lease_seconds),
    )
