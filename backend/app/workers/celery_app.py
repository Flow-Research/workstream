"""Celery application configuration for Workstream workers."""

from __future__ import annotations

from celery import Celery
from celery.exceptions import QueueNotFound
from kombu import Queue
from app.workers.outbox_topology import (
    OUTBOX_DELIVERY_TASK, OUTBOX_QUEUE, OUTBOX_SCAN_TASK, OUTBOX_SCAN_QUEUE,
    FINALIZATION_DELIVERY_TASK, FINALIZATION_QUEUE, is_finalization_worker_process,
    is_outbox_scan_worker_process, FEEDBACK_EMAIL_DELIVERY_TASK, FEEDBACK_EMAIL_QUEUE,
    is_feedback_email_worker_process,
)
from app.workers.source_cleanup_topology import (
    SOURCE_CLEANUP_QUEUE, SOURCE_CLEANUP_TASK, SOURCE_CLEANUP_SCHEDULE,
    is_source_cleanup_worker_process, WorkerTaskBoundary,
)
from app.modules.artifacts.api.submission_cleanup import (
    SUBMISSION_SOURCE_SWEEP_SECONDS, SubmissionSourceCleanupProfile,
)
from app.workers.project_setup_topology import (
    CELERY_VISIBILITY_TIMEOUT_SECONDS,
    PROJECT_GUIDE_CONSUMER_MARKER,
    PROJECT_GUIDE_QUEUE,
)
from celery.signals import beat_init, worker_process_init, worker_process_shutdown, worker_shutdown

from app.adapters.artifacts.internal_workers import (
    initialize_artifact_internal_runtime,
    shutdown_artifact_internal_runtime,
    validate_artifact_internal_runtime_startup,
)
from app.adapters.observability import create_observability_export_adapter
from app.core.config import ARTIFACT_DIRECT_USER_IDENTITY_TIMEOUT_SECONDS, get_settings
from app.core.celery_observability import (
    configure_celery_observability,
    initialize_worker_observability,
    shutdown_celery_parent_observability,
    shutdown_worker_observability,
)
from app.workers.async_runner import run_async_task
from app.workers.errors import CeleryConfigurationError

ARTIFACT_SCRATCH_CLEANUP_TASK = "workstream.artifacts.cleanup_stale_scratch"
ARTIFACT_SCRATCH_CLEANUP_SCHEDULE = "artifact-scratch-cleanup"
ARTIFACT_PUT_RESOLUTION_TASK = "workstream.artifacts.resolve_put_attempt"
ARTIFACT_VERIFICATION_TASK = "workstream.artifacts.verify_object"
ARTIFACT_PENDING_WORK_SCAN_TASK = "workstream.artifacts.scan_pending_work"
ARTIFACT_PENDING_WORK_SCAN_SCHEDULE = "artifact-pending-work-scan"
GUIDE_SETUP_CONTINUATION_TASK = "workstream.artifacts.continue_guide_setup"
GUIDE_SETUP_CONTINUATION_SCAN_TASK = "workstream.artifacts.scan_guide_setup_continuations"
GUIDE_SETUP_CONTINUATION_SCAN_SCHEDULE = "guide-setup-continuation-scan"
PROJECT_CONTROL_QUEUE = "workstream.project_control"
ARTIFACT_WORK_QUEUE = "workstream.artifacts"
PROJECT_GUIDE_COMPILATION_TASK = "workstream.project_setup.compile_project_guide"
POST_POLICY_DERIVATION_TASK = "workstream.project_setup.derive_post_policy"
POST_POLICY_SCAN_TASK = "workstream.project_setup.scan_post_policy_approvals"
RETAINED_REVISION_SCAN_TASK = "workstream.tasks.scan_retained_revisions"
GUIDE_RUNTIME_CLEANUP_TASK = "workstream.project_setup.cleanup_runtime_resources"
OBSERVED_TASK_NAMES = frozenset(
    {
        OUTBOX_DELIVERY_TASK,
        FINALIZATION_DELIVERY_TASK,
        FEEDBACK_EMAIL_DELIVERY_TASK,
        SOURCE_CLEANUP_TASK,
        OUTBOX_SCAN_TASK,
        RETAINED_REVISION_SCAN_TASK,
        POST_POLICY_DERIVATION_TASK,
        POST_POLICY_SCAN_TASK,
        PROJECT_GUIDE_COMPILATION_TASK,
        GUIDE_RUNTIME_CLEANUP_TASK,
        ARTIFACT_SCRATCH_CLEANUP_TASK,
        ARTIFACT_PUT_RESOLUTION_TASK,
        ARTIFACT_VERIFICATION_TASK,
        ARTIFACT_PENDING_WORK_SCAN_TASK,
        GUIDE_SETUP_CONTINUATION_TASK,
        GUIDE_SETUP_CONTINUATION_SCAN_TASK,
    }
)
WORKSTREAM_TASK_ROUTES = {
    PROJECT_GUIDE_COMPILATION_TASK: {"queue": PROJECT_GUIDE_QUEUE},
    POST_POLICY_DERIVATION_TASK: {"queue": PROJECT_CONTROL_QUEUE},
    POST_POLICY_SCAN_TASK: {"queue": PROJECT_CONTROL_QUEUE},
    RETAINED_REVISION_SCAN_TASK: {"queue": PROJECT_CONTROL_QUEUE},
    GUIDE_RUNTIME_CLEANUP_TASK: {"queue": PROJECT_CONTROL_QUEUE},
    ARTIFACT_SCRATCH_CLEANUP_TASK: {"queue": ARTIFACT_WORK_QUEUE},
    ARTIFACT_PUT_RESOLUTION_TASK: {"queue": ARTIFACT_WORK_QUEUE},
    ARTIFACT_VERIFICATION_TASK: {"queue": ARTIFACT_WORK_QUEUE},
    ARTIFACT_PENDING_WORK_SCAN_TASK: {"queue": ARTIFACT_WORK_QUEUE},
    GUIDE_SETUP_CONTINUATION_TASK: {"queue": ARTIFACT_WORK_QUEUE},
    GUIDE_SETUP_CONTINUATION_SCAN_TASK: {"queue": ARTIFACT_WORK_QUEUE},
    OUTBOX_SCAN_TASK: {"queue": OUTBOX_SCAN_QUEUE},
    OUTBOX_DELIVERY_TASK: {"queue": OUTBOX_QUEUE},
    FINALIZATION_DELIVERY_TASK: {"queue": FINALIZATION_QUEUE},
    FEEDBACK_EMAIL_DELIVERY_TASK: {"queue": FEEDBACK_EMAIL_QUEUE},
    SOURCE_CLEANUP_TASK: {"queue": SOURCE_CLEANUP_QUEUE},
}


def _reject_unrouted_task(name, _args, _kwargs, _options, *, task=None):
    """Refuse a publisher that bypasses the closed Workstream task inventory."""
    raise QueueNotFound(f"unrouted Workstream task: {name}")


@worker_process_init.connect
def initialize_artifact_runtime_for_process(**_kwargs: object) -> None:
    """Claim and initialize the artifact provider once per Celery child."""
    if is_source_cleanup_worker_process():
        # Parent validated cleanup startup; each sweep rechecks current authority.
        return
    if (is_finalization_worker_process() or is_outbox_scan_worker_process()
            or is_feedback_email_worker_process()):
        # Scanner, email and finalized replay need no artifact provider.
        # Unfinished finalization initializes its provider on actual observation.
        return
    run_async_task(initialize_artifact_internal_runtime)


@beat_init.connect
def validate_artifact_runtime_for_beat(**_kwargs: object) -> None:
    """Validate the selected provider namespace before Beat schedules work."""
    run_async_task(validate_artifact_internal_runtime_startup)


@worker_process_init.connect
def initialize_observability_for_process(**_kwargs: object) -> None:
    """Create diagnostic providers only in the prefork child."""
    initialize_worker_observability()


@worker_process_shutdown.connect
@worker_shutdown.connect
def shutdown_artifact_runtime_for_process(**_kwargs: object) -> None:
    """Close the artifact provider after any Celery execution pool drains."""
    shutdown_artifact_internal_runtime()


@worker_process_shutdown.connect
def shutdown_observability_for_process(**_kwargs: object) -> None:
    """Bound flushing and close child-owned diagnostic providers."""
    shutdown_worker_observability()


@worker_shutdown.connect
def shutdown_observability_for_parent(**_kwargs: object) -> None:
    """Close any non-prefork runtime and release the broker-parent log lease."""
    shutdown_worker_observability()
    shutdown_celery_parent_observability()


def create_celery_app() -> Celery:
    """Create the Celery application from Workstream settings.

    Returns:
        Configured Celery application for durable background jobs.
    """
    settings = get_settings()
    if settings.submission_source_cleanup_profile is not None:
        SubmissionSourceCleanupProfile.model_validate(settings.submission_source_cleanup_profile)
    broker_url = settings.celery_broker_url
    if broker_url is None:
        if settings.celery_task_always_eager:
            broker_url = "memory://"
        else:
            raise CeleryConfigurationError(
                "WORKSTREAM_CELERY_BROKER_URL must be set for Celery workers"
            )
    celery_app = Celery(
        "workstream",
        task_cls=WorkerTaskBoundary,
        broker=broker_url,
        backend=settings.celery_result_backend_url,
        include=[
            "app.workers.artifacts",
            "app.workers.source_cleanup",
            "app.workers.project_setup",
            "app.workers.post_policy",
            "app.workers.outbox",
            "app.workers.revision_recovery",
        ],
    )
    celery_app.conf.update(
        task_queues=tuple(Queue(name) for name in (
            PROJECT_GUIDE_QUEUE, PROJECT_CONTROL_QUEUE, ARTIFACT_WORK_QUEUE,
            OUTBOX_SCAN_QUEUE, OUTBOX_QUEUE, FINALIZATION_QUEUE, SOURCE_CLEANUP_QUEUE,
            FEEDBACK_EMAIL_QUEUE,
        )),
        task_default_queue=PROJECT_GUIDE_QUEUE,
        task_create_missing_queues=False,
        task_routes=(WORKSTREAM_TASK_ROUTES, _reject_unrouted_task),
        accept_content=["json"],
        result_serializer="json",
        task_always_eager=settings.celery_task_always_eager,
        task_eager_propagates=True,
        task_ignore_result=True,
        task_serializer="json",
        timezone="UTC",
        broker_transport_options={
            "visibility_timeout": CELERY_VISIBILITY_TIMEOUT_SECONDS,
        },
        result_backend_transport_options={
            "visibility_timeout": CELERY_VISIBILITY_TIMEOUT_SECONDS,
        },
        visibility_timeout=CELERY_VISIBILITY_TIMEOUT_SECONDS,
        worker_disable_prefetch=True,
        **{PROJECT_GUIDE_CONSUMER_MARKER: True},
        beat_schedule={
            **({SOURCE_CLEANUP_SCHEDULE: {
                "task": SOURCE_CLEANUP_TASK, "schedule": SUBMISSION_SOURCE_SWEEP_SECONDS,
            }} if settings.submission_source_cleanup_profile is not None else {}),
            "outbox-delivery-recovery": {
                "task": OUTBOX_SCAN_TASK, "schedule": 60.0,
            },
            "retained-revision-recovery": {
                "task": RETAINED_REVISION_SCAN_TASK, "schedule": 60.0,
            },
            "post-policy-approval-recovery": {
                "task": POST_POLICY_SCAN_TASK,
                "schedule": 60.0,
            },
            "guide-runtime-resource-cleanup": {
                "task": GUIDE_RUNTIME_CLEANUP_TASK,
                "schedule": settings.artifact_pending_work_scan_interval_seconds,
            },
            ARTIFACT_SCRATCH_CLEANUP_SCHEDULE: {
                "task": ARTIFACT_SCRATCH_CLEANUP_TASK,
                "schedule": settings.artifact_scratch_cleanup_interval_seconds,
            },
            ARTIFACT_PENDING_WORK_SCAN_SCHEDULE: {
                "task": ARTIFACT_PENDING_WORK_SCAN_TASK,
                "schedule": settings.artifact_pending_work_scan_interval_seconds,
            },
            GUIDE_SETUP_CONTINUATION_SCAN_SCHEDULE: {
                "task": GUIDE_SETUP_CONTINUATION_SCAN_TASK,
                "schedule": settings.artifact_pending_work_scan_interval_seconds,
            },
        },
    )
    if settings.artifact_s3_credential_mode == "aws_access_key":
        # Keep the existing allowance for the DB namespace claim and child handshake.
        celery_app.conf.update(
            worker_proc_alive_timeout=(
                celery_app.conf.worker_proc_alive_timeout
                + ARTIFACT_DIRECT_USER_IDENTITY_TIMEOUT_SECONDS
            ),
        )
    configure_celery_observability(
        settings,
        OBSERVED_TASK_NAMES,
        lambda: create_observability_export_adapter(
            settings, service_name="workstream-celery"
        ),
    )
    return celery_app


celery_app = create_celery_app()
